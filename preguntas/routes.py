from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db import get_conn, db_lock
from utils import get_puntuacion_anterior, get_pregunta_del_dia,get_grupo_actual, get_id_grupo_actual

preguntas_bp = Blueprint("preguntas", __name__)

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    if request.method == "POST":
        id_respuesta = request.form.get("respuesta")
        if not id_respuesta:
            flash("No se ha seleccionado una respuesta.")
            return redirect(url_for("preguntas.ver_pregunta"))

        id_grupo = get_id_grupo_actual(usuario_id) or None
        puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo) or 0

        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")

                # ¿ya respondió hoy?
                cursor.execute("""
                    SELECT 1 FROM Resultados
                    WHERE id_usuario = ? AND DATE(fecha) = ?
                """, (usuario_id, fecha_hoy))
                if cursor.fetchone():
                    flash("Ya has respondido hoy. Solo puedes participar una vez.")
                    return redirect(url_for("index"))

                # respuesta elegida
                cursor.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
                respuesta = cursor.fetchone()
                if not respuesta:
                    flash("Respuesta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                # pregunta asociada
                cursor.execute("SELECT * FROM Preguntas WHERE id = ?", (respuesta["id_pregunta"],))
                pregunta_reg = cursor.fetchone()
                if not pregunta_reg:
                    flash("Pregunta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                # grupo desde sesión (o None)
                grupo_codigo = session.get("grupo_actual")
                id_grupo = None
                if grupo_codigo:
                    cursor.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_codigo,))
                    grupo = cursor.fetchone()
                    if grupo:
                        id_grupo = grupo["id"]

                # puntuación
                correcta = int(respuesta["correcta"])
                puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

                # guardar resultado
                cursor.execute("""
                    INSERT INTO Resultados (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    usuario_id,
                    id_grupo,
                    "2025-T1",
                    puntuacion,
                    correcta,
                    respuesta["id_pregunta"],
                    respuesta["id"]
                ))
                conn.commit()

        # Ya tienes id_grupo calculado arriba; NO reutilices cursor fuera del with
        if id_grupo:
            return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
        else:
            flash("Respuesta registrada. No se detectó grupo; volviendo al inicio.", "error")
            return redirect(url_for("index"))

    # GET: mostrar pregunta
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    # cargar audio/imagen
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

    return render_template("pregunta.html",
                           pregunta=pregunta_actual,
                           respuestas=respuestas,
                           ruta_audio=ruta_audio,
                           ruta_imagen=ruta_imagen)


@preguntas_bp.route("/timeout/<int:pregunta_id>")
def timeout(pregunta_id):
    """Marca la pregunta como INCORRECTA por tiempo agotado (id_respuesta = 99) y redirige a resultados o index."""
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")

            # Si ya respondió hoy, no duplicar
            cursor.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND DATE(fecha) = ?
            """, (usuario_id, fecha_hoy))
            if cursor.fetchone():
                return redirect(url_for("index"))

            # Grupo (desde sesión si existe)
            grupo_codigo = session.get("grupo_actual") or get_grupo_actual(usuario_id)
            id_grupo = None
            if grupo_codigo:
                cursor.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_codigo,))
                g = cursor.fetchone()
                if g:
                    id_grupo = g["id"]

            # Puntuación NO aumenta en timeout
            puntuacion_anterior = get_puntuacion_anterior(usuario_id) or 0

            # Insertar como incorrecta con id_respuesta=99
            cursor.execute("""
                INSERT INTO Resultados (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                usuario_id,
                id_grupo,
                "2025-T1",
                puntuacion_anterior,
                0,              # incorrecta
                pregunta_id,
                0              # código reservado timeout
            ))
            conn.commit()

    # Redirigir a resultados si hay grupo, si no al index
    if id_grupo:
        return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
    return redirect(url_for("index"))

