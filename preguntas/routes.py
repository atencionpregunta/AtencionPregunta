from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

from db import get_conn, db_lock
from utils import (
    get_pregunta_del_dia,       # tu función "clásica" que marca fecha_mostrada (NO-Relámpago)
    ensure_pack_relampago_hoy,  # marca/asegura 3 Relámpago hoy en fecha_mostrada y las devuelve
    get_grupos_usuario,
    ensure_active_temporada,
)

ID_TIMEOUT = 0
ID_MULTIPLE = -1

preguntas_bp = Blueprint("preguntas", __name__)

# ----------------------------
# Zona horaria y utilidades
# ----------------------------
TZ = ZoneInfo("Europe/Madrid")

def ahora_local():
    return datetime.now(TZ)

def ahora_local_str():
    # Texto "YYYY-MM-DD HH:MM:SS" en hora de Madrid
    return ahora_local().strftime("%Y-%m-%d %H:%M:%S")

def hoy_local_str():
    # Texto "YYYY-MM-DD" en fecha de Madrid
    return ahora_local().date().isoformat()

def es_domingo() -> bool:
    # Monday=0 ... Sunday=6
    return ahora_local().weekday() == 2

def nocache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

def es_multiple(conn, pregunta_id: int) -> bool:
    row = conn.execute("""
        SELECT COUNT(*) AS c
        FROM Respuestas
        WHERE id_pregunta = ? AND correcta = 1
    """, (pregunta_id,)).fetchone()
    cnt = int(row[0]) if row else 0
    return cnt > 1

def _tiene_columna(conn, tabla: str, columna: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]
    return columna in cols

def _cargar_pregunta_y_respuestas_por_id(conn, pregunta_id: int):
    """Carga pregunta y respuestas por ID (devuelve (pregunta_dict, respuestas_list))."""
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
    """Devuelve el primer id_pregunta del pack que el usuario NO haya respondido."""
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

    # ---------------- POST: registrar respuesta ----------------
    if request.method == "POST":
        pregunta_id = request.form.get("pregunta_id", type=int)

        # PRE-CÁLCULO: temporada ACTIVA (ID entero) por grupo (fuera de locks)
        temp_id_por_grupo = { g["id"]: ensure_active_temporada(g["id"]) for g in grupos }

        with db_lock:
            with get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys = ON")

                # compat: deducir pregunta_id si no vino
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
                    pregunta_id = row_r["id_pregunta"]

                # ¿ya contestó esta pregunta? → no duplicamos (a nivel de usuario, en cualquier grupo)
                ya = cur.execute("""
                    SELECT 1 FROM Resultados
                    WHERE id_usuario = ? AND id_pregunta = ?
                    LIMIT 1
                """, (usuario_id, pregunta_id)).fetchone()
                if ya:
                    flash("Ya has respondido esta pregunta. Solo se permite una vez por usuario.")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

                # validar pregunta
                if not cur.execute("SELECT 1 FROM Preguntas WHERE id = ?", (pregunta_id,)).fetchone():
                    flash("Pregunta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                # === Datos auxiliares para la vista de respuesta (solo entre semana) ===
                multiple = es_multiple(conn, pregunta_id)

                # ids y textos correctos
                correct_rows = cur.execute("""
                    SELECT id, respuesta
                    FROM Respuestas
                    WHERE id_pregunta = ? AND correcta = 1
                    ORDER BY id
                """, (pregunta_id,)).fetchall()
                correct_ids = {str(r["id"]) for r in correct_rows}
                correct_texts = [r["respuesta"] for r in correct_rows]

                # saber si existe la columna 'seleccion_respuestas'
                tiene_seleccion = _tiene_columna(conn, "Resultados", "seleccion_respuestas")

                # puntuación previa (último registro del usuario)
                row_prev = cur.execute("""
                    SELECT puntuacion
                    FROM Resultados
                    WHERE id_usuario = ?
                    ORDER BY datetime(fecha) DESC
                    LIMIT 1
                """, (usuario_id,)).fetchone()
                puntuacion_anterior = row_prev["puntuacion"] if row_prev else 0

                ahora_txt = ahora_local_str()

                # variables para la vista de respuesta
                fue_correcto = False
                elegidas_texts = []
                seleccion_csv = ""

                if multiple:
                    # múltiple
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
                        temporada_id = temp_id_por_grupo[g["id"]]  # <-- ID entero
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
                    # única
                    id_respuesta = request.form.get("respuesta", type=int)
                    if not id_respuesta:
                        flash("No se ha seleccionado respuesta.")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    r = cur.execute("SELECT correcta, respuesta FROM Respuestas WHERE id = ?", (id_respuesta,)).fetchone()
                    if not r:
                        flash("Respuesta no encontrada.")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    fue_correcto = bool(int(r["correcta"]))
                    correcta_flag = 1 if fue_correcto else 0
                    nueva_puntuacion = puntuacion_anterior + 1 if fue_correcto else puntuacion_anterior

                    # texto elegido y CSV
                    elegidas_texts = [r["respuesta"]]
                    seleccion_csv = str(id_respuesta)

                    for g in grupos:
                        temporada_id = temp_id_por_grupo[g["id"]]  # <-- ID entero
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

                # --- FLUJO ESPECIAL DOMINGO: sin pantalla 'respuesta' ---
                if es_domingo():
                    # Asegura/recupera el pack de hoy (ya marcado en Preguntas.fecha_mostrada)
                    pack = ensure_pack_relampago_hoy()
                    pack_ids = [p["id"] for p in pack]
                    # ¿queda alguna pendiente para este usuario?
                    next_pid = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)
                    if next_pid is None:
                        # Terminó las 3
                        return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))
                    # Aún quedan → volver a GET (servirá la siguiente)
                    return redirect(url_for("preguntas.ver_pregunta"))
                # --- FIN ESPECIAL DOMINGO ---

                # Entre semana: mostrar pantalla de respuesta
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

    # ---------------- GET: mostrar pregunta ----------------
    if es_domingo():
        with db_lock:
            with get_conn() as conn:
                conn.row_factory = sqlite3.Row

                # 1) Asegurar pack Relámpago publicado (marcado en fecha_mostrada hoy)
                pack = ensure_pack_relampago_hoy()   # lista de dicts con al menos 'id'
                if not pack:
                    flash("No hay preguntas relámpago disponibles hoy.")
                    return redirect(url_for("index"))

                # 2) Determinar la siguiente para este usuario (por orden de fecha_mostrada asc)
                pack_ids = [p["id"] for p in pack]
                pid = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)
                if pid is None:
                    # Ya respondió todas las del pack
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

                # 4) Meta UI pack: índice (0-based) y total
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
                    # meta pack domingo
                    is_pack_domingo=True,
                    pack_idx=idx,
                    pack_total=total,
                    btn_label=btn_label
                ))
                return nocache(resp)

    # --- No es domingo: 1 sola pregunta normal (tu util clásico) ---
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    try:
        pid = pregunta_actual["id"]
    except Exception:
        pid = pregunta_actual.id

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
        # meta pack domingo desactivada
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

    # PRE-CÁLCULO: temporada ACTIVA (ID entero) por grupo (fuera de lock)
    temp_id_por_grupo = { g["id"]: ensure_active_temporada(g["id"]) for g in grupos }

    with db_lock:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")

            # ¿ya registró algo hoy? (hora local) → evita duplicados de timeout
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
            puntuacion_anterior = row_prev["puntuacion"] if row_prev else 0

            ahora_txt = ahora_local_str()
            tiene_seleccion = _tiene_columna(conn, "Resultados", "seleccion_respuestas")

            for g in grupos:
                temporada_id = temp_id_por_grupo[g["id"]]  # <-- ID entero
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

            # Domingo: ¿quedan publicadas pendientes?
            if es_domingo():
                pack = ensure_pack_relampago_hoy()
                pack_ids = [p["id"] for p in pack]
                siguiente = _siguiente_relampago_pendiente(conn, usuario_id, pack_ids)
                if siguiente is not None:
                    return redirect(url_for("preguntas.ver_pregunta"))

    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))
