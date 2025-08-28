from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import sqlite3
from db import get_conn, db_lock
from utils import get_puntuacion_anterior, get_pregunta_del_dia, get_grupos_usuario

preguntas_bp = Blueprint("preguntas", __name__)

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    # Requiere sesión
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]

    # Debe pertenecer a ≥1 grupo
    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para continuar.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    # ------------------ POST: procesar respuesta ------------------
    if request.method == "POST":
        id_respuesta = request.form.get("respuesta", type=int)
        if not id_respuesta:
            flash("No se ha seleccionado una respuesta.")
            return redirect(url_for("preguntas.ver_pregunta"))

        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")

                # 1) Respuesta elegida
                cursor.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
                respuesta = cursor.fetchone()
                if not respuesta:
                    flash("Respuesta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                pregunta_id = respuesta["id_pregunta"]

                # 2) Evitar duplicado global (usuario+pregunta en cualquier grupo)
                cursor.execute("""
                    SELECT 1
                    FROM Resultados
                    WHERE id_usuario = ? AND id_pregunta = ?
                    LIMIT 1
                """, (usuario_id, pregunta_id))
                if cursor.fetchone():
                    flash("Ya has respondido esta pregunta. Solo se permite una vez por usuario.")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

                # 3) Validar que la pregunta exista
                cursor.execute("SELECT 1 FROM Preguntas WHERE id = ?", (pregunta_id,))
                if not cursor.fetchone():
                    flash("Pregunta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                # 4) Puntuación previa global (último registro)
                cursor.execute("""
                    SELECT puntuacion
                    FROM Resultados
                    WHERE id_usuario = ?
                    ORDER BY datetime(fecha) DESC
                    LIMIT 1
                """, (usuario_id,))
                row_prev = cursor.fetchone()
                puntuacion_anterior = row_prev["puntuacion"] if row_prev else 0

                # 5) Calcular nueva puntuación
                correcta = int(respuesta["correcta"])  # cambia a ["es_correcta"] si tu columna se llama así
                nueva_puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

                # 6) Insertar un resultado por CADA grupo
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for g in grupos:
                    # Si tienes UNIQUE(id_usuario,id_grupo,id_pregunta), esto ignora carreras/duplicados
                    cursor.execute("""
                        INSERT OR IGNORE INTO Resultados
                            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ahora,
                        usuario_id,
                        g["id"],
                        "2025-T1",      # ajusta si calculas temporada dinámicamente
                        nueva_puntuacion,
                        correcta,
                        pregunta_id,
                        respuesta["id"]
                    ))
                conn.commit()

        # 7) Redirección post-inserción: resultados del primer grupo
        return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

    # ------------------ GET: mostrar pregunta ------------------
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    # ID de la pregunta (dict u objeto)
    try:
        pregunta_id = pregunta_actual["id"]
    except Exception:
        pregunta_id = pregunta_actual.id

    # Extras (audio/imagen)
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

    return render_template(
        "pregunta.html",
        pregunta=pregunta_actual,
        respuestas=respuestas,
        ruta_audio=ruta_audio,
        ruta_imagen=ruta_imagen
    )


@preguntas_bp.route("/timeout/<int:pregunta_id>")
def timeout(pregunta_id):
    """
    Marca la pregunta como INCORRECTA por tiempo agotado en TODOS los grupos del usuario (id_respuesta = 0)
    y redirige a resultados del primer grupo.
    """
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para continuar.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")

            # Evitar duplicado de "respuesta hoy" (global)
            cursor.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND DATE(fecha) = ?
                LIMIT 1
            """, (usuario_id, fecha_hoy))
            if cursor.fetchone():
                return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))

            # Puntuación previa global (no aumenta en timeout)
            cursor.execute("""
                SELECT puntuacion
                FROM Resultados
                WHERE id_usuario = ?
                ORDER BY datetime(fecha) DESC
                LIMIT 1
            """, (usuario_id,))
            row_prev = cursor.fetchone()
            puntuacion_anterior = row_prev["puntuacion"] if row_prev else 0

            # Insertar incorrecta (id_respuesta=0 reservado para timeout) en TODOS los grupos
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for g in grupos:
                cursor.execute("""
                    INSERT OR IGNORE INTO Resultados
                        (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ahora,
                    usuario_id,
                    g["id"],
                    "2025-T1",
                    puntuacion_anterior,
                    0,          # incorrecta
                    pregunta_id,
                    0           # timeout
                ))
            conn.commit()

    return redirect(url_for("resultados.ver_resultados", id_grupo=grupos[0]["id"]))
