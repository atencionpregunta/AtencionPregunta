# preguntas.py (Blueprint)
from __future__ import annotations
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response
import sqlite3

from db import get_conn, db_lock
from utils import (
    ahora_local_str,
    hoy_local_str,
    get_pregunta_del_dia,
    ensure_pack_relampago_hoy,
    get_grupos_usuario,
    ensure_active_temporada,
    es_domingo,
)

ID_TIMEOUT = 0
ID_MULTIPLE = -1

preguntas_bp = Blueprint("preguntas", __name__)

# ----------------------------
# Helpers locales
# ----------------------------
def _tiene_columna(conn, tabla: str, columna: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]
    return columna in cols

def es_multiple(conn, pregunta_id: int) -> bool:
    row = conn.execute("""
        SELECT COUNT(*) AS c
        FROM Respuestas
        WHERE id_pregunta = ? AND correcta = 1
    """, (pregunta_id,)).fetchone()
    cnt = int(row[0]) if row else 0
    return cnt > 1

def _cargar_pregunta_y_respuestas_por_id(conn, pregunta_id: int):
    conn.row_factory = sqlite3.Row
    q = conn.execute("SELECT * FROM Preguntas WHERE id = ?", (pregunta_id,)).fetchone()
    if not q:
        return None, []
    rs = conn.execute("""
        SELECT id, respuesta, correcta
        FROM Respuestas
        WHERE id_pregunta = ?
        ORDER BY id
    """, (pregunta_id,)).fetchall()
    return dict(q), [dict(r) for r in rs]

def _siguiente_relampago_pendiente(conn, usuario_id: int, pack_ids: list[int]) -> int | None:
    if not pack_ids:
        return None
    marks = ",".join(["?"] * len(pack_ids))
    responded = set(int(r[0]) for r in conn.execute(
        f"SELECT id_pregunta FROM Resultados WHERE id_usuario = ? AND id_pregunta IN ({marks})",
        [usuario_id] + pack_ids
    ).fetchall())
    for pid in pack_ids:
        if pid not in responded:
            return pid
    return None

def nocache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

# ----------------------------
# Rutas
# ----------------------------
@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para continuar.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    # --------------- POST: registrar respuesta ---------------
    if request.method == "POST":
        pregunta_id = request.form.get("pregunta_id", type=int)

        # PRE: temporada activa por grupo (fuera de locks)
        temp_id_por_grupo = { g["id"]: ensure_active_temporada(g["id"]) for g in grupos }

        with db_lock:
            with get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys = ON")

                # Deducir pregunta si no vino
                if not pregunta_id:
                    id_resp_tmp = request.form.get("respuesta", type=int)
                    if not id_resp_tmp:
                        flash("No se ha seleccionado respuesta.")
                        return redirect(url_for("preguntas.ver_pregunta"))
                    row_r = cur.execute(
                        "SELECT id_pregunta FROM Respuestas WHERE id = ?",
                        (id_resp_tmp,)
                    ).fetchone()
                    if not row_r:
                        flash("Respuesta no encontrada.")
                        return redirect(url_for("preguntas.ver_pregunta"))
                    pregunta_id = int(row_r["id_pregunta"])

                # ¿ya contestó esta pregunta?
                ya = cur.execute("""
                    SELECT 1 FROM Resultados
                    WHERE id_usuario = ? AND id_pregunta = ?
                    LIMIT 1
                """, (usuario_id, pregunta_id)).fetchone()
                if ya:
                    flash("Ya has respondido esta pregunta. Solo se permite una vez por usuario.")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

                # validar pregunta
                ex = cur.execute("SELECT 1 FROM Preguntas WHERE id = ?", (pregunta_id,)).fetchone()
                if not ex:
                    flash("Pregunta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                multiple = es_multiple(conn, pregunta_id)

                # correctas
                correct_rows = cur.execute("""
                    SELECT id, respuesta
                    FROM Respuestas
                    WHERE id_pregunta = ? AND correcta = 1
                    ORDER BY id
                """, (pregunta_id,)).fetchall()
                correct_ids = {str(r["id"]) for r in correct_rows}
                correct_texts = [r["respuesta"] for r in correct_rows]

                # ¿existe columna seleccion_respuestas?
                tiene_seleccion = _tiene_columna(conn, "Resultados", "seleccion_respuestas")

                # puntuación previa global del usuario (último registro)
                row_prev = cur.execute("""
                    SELECT puntuacion
                    FROM Resultados
                    WHERE id_usuario = ?
                    ORDER BY datetime(fecha) DESC
                    LIMIT 1
                """, (usuario_id,)).fetchone()
                puntuacion_anterior = int(row_prev["puntuacion"]) if row_prev and row_prev["puntuacion"] is not None else 0

                ahora_txt = ahora_local_str()

                # variables para vista respuesta
                fue_correcto = False
                elegidas_texts = []
                seleccion_csv = ""

                if multiple:
                    seleccionadas = request.form.getlist("respuestas_seleccionadas")
                    if not seleccionadas:
                        flash("No has seleccionado ninguna respuesta.")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    sel_set = set(seleccionadas)
                    fue_correcto = (sel_set == correct_ids)
                    correcta_flag = 1 if fue_correcto else 0
                    nueva_puntuacion = puntuacion_anterior + 1 if fue_correcto else puntuacion_anterior
                    seleccion_csv = "/".join(sorted(sel_set, key=int))

                    # textos elegidos
                    if sel_set:
                        qmarks = ",".join(["?"] * len(sel_set))
                        rows = cur.execute(f"""
                            SELECT respuesta FROM Respuestas
                            WHERE id IN ({qmarks})
                            ORDER BY id
                        """, list(sel_set)).fetchall()
                        elegidas_texts = [r["respuesta"] for r in rows]

                    for g in grupos:
                        temporada_id = temp_id_por_grupo[g["id"]]
                        if tiene_seleccion:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta, seleccion_respuestas)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], temporada_id,
                                nueva_puntuacion, correcta_flag,
                                pregunta_id, ID_MULTIPLE, seleccion_csv
                            ))
                        else:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], temporada_id,
                                nueva_puntuacion, correcta_flag,
                                pregunta_id, ID_MULTIPLE
                            ))
                    conn.commit()

                else:
                    id_respuesta = request.form.get("respuesta", type=int)
                    if not id_respuesta:
                        flash("No se ha seleccionado respuesta.")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    r = cur.execute(
                        "SELECT correcta, respuesta FROM Respuestas WHERE id = ?",
                        (id_respuesta,)
                    ).fetchone()
                    if not r:
                        flash("Respuesta no encontrada.")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    fue_correcto = bool(int(r["correcta"]))
                    correcta_flag = 1 if fue_correcto else 0
                    nueva_puntuacion = puntuacion_anterior + 1 if fue_correcto else puntuacion_anterior

                    elegidas_texts = [r["respuesta"]]
                    seleccion_csv = str(id_respuesta)

                    for g in grupos:
                        temporada_id = temp_id_por_grupo[g["id"]]
                        if tiene_seleccion:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta, seleccion_respuestas)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], temporada_id,
                                nueva_puntuacion, correcta_flag,
                                pregunta_id, id_respuesta, seleccion_csv
                            ))
                        else:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], temporada_id,
                                nueva_puntuacion, correcta_flag,
                                pregunta_id, id_respuesta
                            ))
                    conn.commit()

                # --- Flujo domingo (pack Relámpago) ---
                    if es_domingo():
                        pack = ensure_pack_relampago_hoy()
                        pack_ids = [int(p["id"]) for p in pack]
                        next_pid = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)

                        if next_pid is not None:
                            # Aún quedan preguntas del pack: volvemos a mostrar la siguiente pregunta
                            return redirect(url_for("preguntas.ver_pregunta"))

                        # No quedan preguntas: construimos los 3 bloques y mostramos TODO en respuesta.html
                        bloques_relampago = []

                        # ¿existe la columna seleccion_respuestas?
                        tiene_sel = _tiene_columna(conn, "Resultados", "seleccion_respuestas")

                        for i, pid in enumerate(pack_ids, start=1):
                            # Textos correctos de esa pregunta
                            correct_rows = conn.execute(
                                """SELECT respuesta FROM Respuestas
                                WHERE id_pregunta = ? AND correcta = 1
                                ORDER BY id""",
                                (pid,)
                            ).fetchall()
                            correctas = [r["respuesta"] for r in correct_rows]

                            # Fun fact (si existe)
                            fun_fact = None
                            if _tiene_columna(conn, "Preguntas", "fun_fact"):
                                row_ff = conn.execute(
                                    "SELECT fun_fact FROM Preguntas WHERE id = ?",
                                    (pid,)
                                ).fetchone()
                                fun_fact = (row_ff["fun_fact"] or None) if row_ff else None

                            # Último resultado del usuario para esa pregunta del pack
                            # Nota: si hay seleccion_respuestas la parseamos; si no, usamos id_respuesta
                            if tiene_sel:
                                rusr = conn.execute(
                                    """SELECT correcta, id_respuesta, seleccion_respuestas
                                    FROM Resultados
                                    WHERE id_usuario = ? AND id_pregunta = ?
                                    ORDER BY datetime(fecha) DESC
                                    LIMIT 1""",
                                    (usuario_id, pid)
                                ).fetchone()
                            else:
                                rusr = conn.execute(
                                    """SELECT correcta, id_respuesta, NULL AS seleccion_respuestas
                                    FROM Resultados
                                    WHERE id_usuario = ? AND id_pregunta = ?
                                    ORDER BY datetime(fecha) DESC
                                    LIMIT 1""",
                                    (usuario_id, pid)
                                ).fetchone()

                            correcto_b = bool(int(rusr["correcta"])) if rusr and rusr["correcta"] is not None else False
                            elegidas = []

                            if rusr:
                                if tiene_sel and rusr["seleccion_respuestas"]:
                                    ids = [x for x in str(rusr["seleccion_respuestas"]).split("/") if x.strip().isdigit()]
                                    if ids:
                                        qm = ",".join(["?"] * len(ids))
                                        rows_e = conn.execute(
                                            f"SELECT respuesta FROM Respuestas WHERE id IN ({qm}) ORDER BY id",
                                            list(map(int, ids))
                                        ).fetchall()
                                        elegidas = [e["respuesta"] for e in rows_e]
                                else:
                                    # Caso single: id_respuesta (si no es TIMEOUT/ID_MULTIPLE)
                                    if rusr["id_respuesta"] and int(rusr["id_respuesta"]) > 0:
                                        row_e = conn.execute(
                                            "SELECT respuesta FROM Respuestas WHERE id = ?",
                                            (int(rusr["id_respuesta"]),)
                                        ).fetchone()
                                        if row_e:
                                            elegidas = [row_e["respuesta"]]

                            bloques_relampago.append({
                                "titulo": f"Pregunta {i}",
                                "correcto": correcto_b,
                                "correctas": correctas,
                                "elegidas": elegidas,
                                "fun_fact": fun_fact
                            })

                        # Renderizamos respuesta.html mostrando los 3 bloques y CTA a clasificación
                        resp = make_response(render_template(
                            "respuesta.html",
                            bloques_relampago=bloques_relampago,
                            # Si quieres también mostrar la última elección puntual:
                            correcto=fue_correcto,
                            correctas=correct_texts,
                            elegidas=elegidas_texts,
                            fun_fact=fun_fact,  # el de la última pregunta contestada, opcional
                            ruta_mascota=url_for("static", filename="img/ATPPet-nerd.png"),
                            mostrar_cta=True  # para un botón “Ver clasificación”
                        ))
                        return nocache(resp)



                # Entre semana: pantalla de respuesta con fun_fact (si existe)
                fun_fact = None
                if _tiene_columna(conn, "Preguntas", "fun_fact"):
                    ff = cur.execute("SELECT fun_fact FROM Preguntas WHERE id = ?", (pregunta_id,)).fetchone()
                    fun_fact = ff["fun_fact"] if ff and ff["fun_fact"] else None

                resp = make_response(render_template(
                    "respuesta.html",
                    correcto=fue_correcto,
                    correctas=correct_texts,
                    elegidas=elegidas_texts,
                    fun_fact=fun_fact,
                    ruta_mascota=url_for("static", filename="img/ATPPet-nerd.png")
                ))
                return nocache(resp)

    # --------------- GET: mostrar pregunta ---------------
    if es_domingo():
        with db_lock:
            with get_conn() as conn:
                conn.row_factory = sqlite3.Row

                # 1) Asegurar pack Relámpago publicado (jornada actual)
                pack = ensure_pack_relampago_hoy()
                if not pack:
                    flash("No hay preguntas relámpago disponibles hoy.")
                    return redirect(url_for("index"))

                # 2) Determinar la siguiente pendiente para este usuario
                pack_ids = [p["id"] for p in pack]
                pid = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)
                if pid is None:
                    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

                # 3) Cargar pregunta, respuestas y extras
                pregunta_actual, respuestas = _cargar_pregunta_y_respuestas_por_id(conn, pid)
                if not pregunta_actual:
                    flash("No se ha podido cargar la pregunta.")
                    return redirect(url_for("index"))

                extra = conn.execute("SELECT ruta_audio, ruta_imagen FROM Preguntas WHERE id = ?", (pid,)).fetchone()
                ruta_audio = extra["ruta_audio"] if extra else None
                ruta_imagen = extra["ruta_imagen"] if extra else None
                multiple = es_multiple(conn, pid)

                # 4) Meta pack: índice y total
                idx = pack_ids.index(pid)
                total = len(pack_ids)
                btn_label = "Siguiente pregunta" if idx < total - 1 else "Enviar y terminar"


                
                resp = make_response(render_template(
                    "pregunta.html",
                    pregunta=pregunta_actual,
                    respuestas=respuestas,
                    ruta_audio=ruta_audio,
                    ruta_imagen=ruta_imagen,
                    es_multiple=multiple,
                    is_pack_domingo=True,
                    pack_idx=idx,
                    pack_total=total,
                    btn_label=btn_label
                ))
                return nocache(resp)

    # --- No es domingo: 1 sola pregunta normal ---
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    try:
        pid = int(pregunta_actual["id"])
    except Exception:
        pid = int(pregunta_actual.id)

    with db_lock:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT ruta_audio, ruta_imagen
                FROM Preguntas
                WHERE id = ?
            """, (pid,))
            extra = cur.fetchone()
            ruta_audio = extra["ruta_audio"] if extra else None
            ruta_imagen = extra["ruta_imagen"] if extra else None
            multiple = es_multiple(conn, pid)

    resp = make_response(render_template(
        "pregunta.html",
        pregunta=pregunta_actual,
        respuestas=respuestas,
        ruta_audio=ruta_audio,
        ruta_imagen=ruta_imagen,
        es_multiple=multiple,
        is_pack_domingo=False,
        pack_idx=None,
        pack_total=None,
        btn_label="Enviar respuesta"
    ))
    return nocache(resp)

@preguntas_bp.route("/timeout/<int:pregunta_id>")
def timeout(pregunta_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = hoy_local_str()
    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para continuar.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    # PRE: temporada activa por grupo
    temp_id_por_grupo = { g["id"]: ensure_active_temporada(g["id"]) for g in grupos }

    with db_lock:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")

            # Evitar duplicados de timeout el mismo día calendario local
            ya_hoy = cur.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ?
                  AND DATE(fecha, 'localtime') = ?
                LIMIT 1
            """, (usuario_id, fecha_hoy)).fetchone()
            if ya_hoy:
                return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

            row_prev = cur.execute("""
                SELECT puntuacion
                FROM Resultados
                WHERE id_usuario = ?
                ORDER BY datetime(fecha) DESC
                LIMIT 1
            """, (usuario_id,)).fetchone()
            puntuacion_anterior = int(row_prev["puntuacion"]) if row_prev and row_prev["puntuacion"] is not None else 0

            ahora_txt = ahora_local_str()
            tiene_seleccion = _tiene_columna(conn, "Resultados", "seleccion_respuestas")

            for g in grupos:
                temporada_id = temp_id_por_grupo[g["id"]]
                if tiene_seleccion:
                    cur.execute("""
                        INSERT OR IGNORE INTO Resultados
                            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                             id_pregunta, id_respuesta, seleccion_respuestas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ahora_txt, usuario_id, g["id"], temporada_id,
                        puntuacion_anterior, 0,
                        pregunta_id, ID_TIMEOUT, "[TIMEOUT]"
                    ))
                else:
                    cur.execute("""
                        INSERT OR IGNORE INTO Resultados
                            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                             id_pregunta, id_respuesta)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ahora_txt, usuario_id, g["id"], temporada_id,
                        puntuacion_anterior, 0,
                        pregunta_id, ID_TIMEOUT
                    ))
            conn.commit()

            # Domingo (pack): si quedan pendientes, seguir
            if es_domingo():
                pack = ensure_pack_relampago_hoy()
                pack_ids = [p["id"] for p in pack]
                siguiente = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)
                if siguiente is not None:
                    return redirect(url_for("preguntas.ver_pregunta"))

    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))
