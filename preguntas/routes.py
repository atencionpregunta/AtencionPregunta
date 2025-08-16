from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db import get_conn, db_lock
from utils import get_puntuacion_anterior, get_pregunta_del_dia,get_grupo_actual

preguntas_bp = Blueprint("preguntas", __name__)

from sqlite3 import IntegrityError

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    if request.method == "POST":
        # 1) Validar que viene la respuesta y tiparla a int
        id_respuesta_str = request.form.get("respuesta")
        if not id_respuesta_str:
            flash("No se ha seleccionado una respuesta.", "error")
            return redirect(url_for("preguntas.ver_pregunta"))
        try:
            id_respuesta = int(id_respuesta_str)
        except ValueError:
            flash("Respuesta inválida.", "error")
            return redirect(url_for("preguntas.ver_pregunta"))

        puntuacion_anterior = get_puntuacion_anterior(usuario_id) or 0

        try:
            with db_lock:
                with get_conn() as conn:
                    c = conn.cursor()
                    c.execute("PRAGMA foreign_keys = ON")

                    # 2) Evitar doble participación hoy (por fecha)
                    c.execute("""
                        SELECT 1 FROM Resultados
                        WHERE id_usuario = ? AND DATE(fecha) = ?
                        LIMIT 1
                    """, (usuario_id, fecha_hoy))
                    if c.fetchone():
                        flash("Ya has respondido hoy. Solo puedes participar una vez.", "warning")
                        return redirect(url_for("index"))

                    # 3) Cargar pregunta del día FIJADA hoy
                    hoy = datetime.now().date().isoformat()
                    c.execute("""
                        SELECT * FROM Preguntas
                        WHERE substr(COALESCE(fecha_mostrada,''),1,10) = ?
                        LIMIT 1
                    """, (hoy,))
                    preg_hoy = c.fetchone()
                    if not preg_hoy:
                        flash("No hay pregunta fijada para hoy.", "error")
                        return redirect(url_for("index"))
                    id_pregunta_hoy = preg_hoy["id"]

                    # 4) Cargar la respuesta enviada y verificar que pertenece a la pregunta de hoy
                    c.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
                    resp = c.fetchone()
                    if not resp:
                        flash("La respuesta seleccionada no existe.", "error")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    if resp["id_pregunta"] != id_pregunta_hoy:
                        # Esto evita que alguien envíe una respuesta de otra pregunta y rompa FK/coherencia
                        flash("La respuesta no corresponde a la pregunta del día.", "error")
                        return redirect(url_for("preguntas.ver_pregunta"))

                    # 5) Resolver grupo (aceptamos NULL si no hay)
                    id_grupo = None
                    grupo_codigo = session.get("grupo_actual")
                    if grupo_codigo:
                        c.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_codigo,))
                        row_g = c.fetchone()
                        if row_g:
                            id_grupo = row_g["id"]
                        else:
                            # Si el código de sesión ya no existe en BD, lo limpiamos para no romper FK
                            session.pop("grupo_actual", None)

                    # 6) Calcular nueva puntuación
                    correcta = int(resp["correcta"])  # 0/1
                    puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

                    # 7) Insertar resultado (todas las FK ahora están garantizadas)
                    c.execute("""
                        INSERT INTO Resultados
                        (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        usuario_id,
                        id_grupo,               # puede ser None y es válido
                        "2025-T1",
                        puntuacion,
                        correcta,
                        id_pregunta_hoy,
                        id_respuesta
                    ))
                    conn.commit()

        except IntegrityError as e:
            # Si algo de FK falla, lo verás claro en el flash y no revienta a 500
            flash(f"Error de integridad en la base de datos (FK). Detalle: {e}", "error")
            return redirect(url_for("preguntas.ver_pregunta"))
        except Exception as e:
            # Cualquier otro error, también lo mostramos y evitamos el 500
            flash(f"Ocurrió un error al guardar tu respuesta: {e}", "error")
            return redirect(url_for("preguntas.ver_pregunta"))

        # Redirección tras guardar
        if id_grupo:
            return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
        else:
            flash("Respuesta registrada. (Sin grupo activo).", "success")
            return redirect(url_for("index"))

    # --- GET: Mostrar pregunta del día como ya lo tienes ---
    # ...


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

