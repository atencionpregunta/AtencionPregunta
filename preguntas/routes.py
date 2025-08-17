from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db import get_conn, db_lock
from utils import get_puntuacion_anterior, get_pregunta_del_dia,get_grupo_actual, get_id_grupo_actual

preguntas_bp = Blueprint("preguntas", __name__)

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    # Requiere sesión
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    id_grupo = get_id_grupo_actual(usuario_id)

    # ------------------ POST: procesar respuesta ------------------
    if request.method == "POST":
        id_respuesta = request.form.get("respuesta")
        if not id_respuesta:
            flash("No se ha seleccionado una respuesta.")
            return redirect(url_for("preguntas.ver_pregunta"))

        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")

                # 1) Obtener la respuesta elegida
                cursor.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
                respuesta = cursor.fetchone()
                if not respuesta:
                    flash("Respuesta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                pregunta_id = respuesta["id_pregunta"]

                # 2) Evitar duplicado: ¿este usuario ya respondió ESTA pregunta?
                cursor.execute("""
                    SELECT 1
                    FROM Resultados
                    WHERE id_usuario = ? AND id_pregunta = ?
                    LIMIT 1
                """, (usuario_id, pregunta_id))
                if cursor.fetchone():
                    # Ya había respondido esta pregunta → redirige a resultados (si hay grupo) o al inicio
                    flash("Ya has respondido esta pregunta. Solo se permite una vez por usuario.")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo)) if id_grupo else redirect(url_for("index"))

                # 3) (Opcional) validar que la pregunta exista
                cursor.execute("SELECT * FROM Preguntas WHERE id = ?", (pregunta_id,))
                pregunta_reg = cursor.fetchone()
                if not pregunta_reg:
                    flash("Pregunta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                # 4) Puntuación previa global del usuario (último registro)
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
                correcta = int(respuesta["correcta"])
                nueva_puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

                # 6) Insertar resultado
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    cursor.execute("""
                        INSERT INTO Resultados
                            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ahora,
                        usuario_id,
                        id_grupo,           # Guardamos el grupo para poder ver rankings por grupo
                        "2025-T1",          # Ajusta si tienes cálculo dinámico de temporada
                        nueva_puntuacion,
                        correcta,
                        pregunta_id,
                        respuesta["id"]
                    ))
                    conn.commit()
                except sqlite3.IntegrityError:
                    # Por si tienes un índice único (id_usuario, id_pregunta) y hubo doble tap/carrera
                    flash("Ya habías respondido esta pregunta.")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo)) if id_grupo else redirect(url_for("index"))

        # 7) Redirección post-inserción
        if id_grupo:
            return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
        else:
            flash("Respuesta registrada. No se detectó grupo; volviendo al inicio.")
            return redirect(url_for("index"))

    # ------------------ GET: mostrar pregunta ------------------
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    # Obtener id de la pregunta (Row u objeto)
    try:
        pregunta_id = pregunta_actual["id"]
    except Exception:
        pregunta_id = pregunta_actual.id

    # Cargar rutas de audio/imagen si existen
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
            id_grupo = get_id_grupo_actual(usuario_id) or None
            puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo) or 0

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

