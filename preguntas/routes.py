from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

from db import get_conn, db_lock
from utils import get_pregunta_del_dia, get_grupos_usuario

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

        with db_lock:
            with get_conn() as conn:
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

                # ¿ya contestó esta pregunta? → sigue y muestra resultados (no duplicamos)
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

                # === Datos auxiliares para REVELAR respuesta (⬅️ CAMBIO) ===
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

                # variables para la vista de respuesta (⬅️ CAMBIO)
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
                        if tiene_seleccion:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta, seleccion_respuestas)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], "2025-T1",
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
                                ahora_txt, usuario_id, g["id"], "2025-T1",
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
                        if tiene_seleccion:
                            cur.execute("""
                                INSERT OR IGNORE INTO Resultados
                                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                                     id_pregunta, id_respuesta, seleccion_respuestas)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ahora_txt, usuario_id, g["id"], "2025-T1",
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
                                ahora_txt, usuario_id, g["id"], "2025-T1",
                                nueva_puntuacion, correcta_flag,
                                pregunta_id, id_respuesta
                            ))
                    conn.commit()

                # Fun Fact y assets (⬅️ CAMBIO)
                fun_fact = None
                if _tiene_columna(conn, "Preguntas", "fun_fact"):
                    ff = cur.execute("SELECT fun_fact FROM Preguntas WHERE id = ?", (pregunta_id,)).fetchone()
                    fun_fact = ff["fun_fact"] if ff and ff["fun_fact"] else None

                # Renderizar PÁGINA INTERMEDIA de revelado (⬅️ CAMBIO)
                resp = make_response(render_template(
                    "respuesta.html",
                    correcto=fue_correcto,
                    correctas=correct_texts,      # lista de textos correctos
                    elegidas=elegidas_texts,      # lista de textos que marcó
                    fun_fact=fun_fact,
                    ruta_mascota=url_for("static", filename="img\ATPPet-nerd.png")  # ajusta si usas otra ruta
                ))
                return nocache(resp)

        # (antes se hacía redirect a resultados, ya NO)  # ⬅️ CAMBIO
        # return redirect(url_for("res", id_grupo=grupos[0]["id"]))

    # ---------------- GET: mostrar pregunta ----------------
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    try:
        pregunta_id = pregunta_actual["id"]
    except Exception:
        pregunta_id = pregunta_actual.id

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT ruta_audio, ruta_imagen
                FROM Preguntas
                WHERE id = ?
            """, (pregunta_id,))
            extra = cur.fetchone()
            ruta_audio = extra["ruta_audio"] if extra else None
            ruta_imagen = extra["ruta_imagen"] if extra else None
            multiple = es_multiple(conn, pregunta_id)

    resp = make_response(render_template(
        "pregunta.html",
        pregunta=pregunta_actual,
        respuestas=respuestas,
        ruta_audio=ruta_audio,
        ruta_imagen=ruta_imagen,
        es_multiple=multiple
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

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")

            # IMPORTANTE: comparar con fecha local en SQLite
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
                if tiene_seleccion:
                    cur.execute("""
                        INSERT OR IGNORE INTO Resultados
                            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta,
                             id_pregunta, id_respuesta, seleccion_respuestas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ahora_txt, usuario_id, g["id"], "2025-T1",
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
                        ahora_txt, usuario_id, g["id"], "2025-T1",
                        puntuacion_anterior, 0,
                        pregunta_id, ID_TIMEOUT
                    ))
            conn.commit()

    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))
