from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db import get_conn, db_lock
from utils import get_puntuacion_anterior, get_pregunta_del_dia, get_grupo_actual

preguntas_bp = Blueprint("preguntas", __name__)

def _get_id_grupo_activo(usuario_id):
    """Obtiene el id_grupo a partir del código en sesión o el primero del usuario. Lanza si no hay."""
    codigo = session.get("grupo_actual") or get_grupo_actual(usuario_id)
    if not codigo:
        raise RuntimeError("No hay grupo activo para el usuario.")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM Grupos WHERE codigo = ?", (codigo,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("El grupo activo no existe en BD.")
        return row["id"]

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]

    if request.method == "POST":
        id_respuesta = request.form.get("respuesta")
        if not id_respuesta:
            flash("No se ha seleccionado una respuesta.")
            return redirect(url_for("preguntas.ver_pregunta"))

        with db_lock:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys = ON")

                # 1) Respuesta elegida + su pregunta
                cur.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
                resp = cur.fetchone()
                if not resp:
                    flash("Respuesta no encontrada.")
                    return redirect(url_for("preguntas.ver_pregunta"))

                id_pregunta = resp["id_pregunta"]

                # 2) Grupo activo (ANTES de calcular puntuación)
                try:
                    id_grupo = _get_id_grupo_activo(usuario_id)
                except RuntimeError as e:
                    flash(str(e), "error")
                    return redirect(url_for("index"))

                # 3) Evitar doble participación en esta misma pregunta (por usuario+grupo)
                cur.execute("""
                    SELECT 1 FROM Resultados
                    WHERE id_usuario=? AND id_pregunta=?
                """, (usuario_id, id_pregunta))
                if cur.fetchone():
                    flash("Ya has respondido la pregunta de hoy en este grupo.", "error")
                    return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

                # 4) Puntuación anterior (scoped por grupo)
                puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo)  # debe devolver 0 si no hay
                correcta = int(resp["correcta"])
                nueva_puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

                # 5) Insertar resultado
                cur.execute("""
                    INSERT INTO Resultados
                    (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    usuario_id,
                    id_grupo,
                    "2025-T1",
                    nueva_puntuacion,
                    correcta,
                    id_pregunta,
                    resp["id"]
                ))
                conn.commit()

        return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

    # GET: cargar pregunta del día + recursos
    pregunta, respuestas = get_pregunta_del_dia()
    if not pregunta:
        flash("No se ha podido cargar la pregunta del día.")
        return redirect(url_for("index"))

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ruta_audio, ruta_imagen FROM Preguntas WHERE id = ?", (pregunta["id"],))
            extra = cur.fetchone() or {}
            ruta_audio = extra.get("ruta_audio")
            ruta_imagen = extra.get("ruta_imagen")

    return render_template("pregunta.html",
                           pregunta=pregunta,
                           respuestas=respuestas,
                           ruta_audio=ruta_audio,
                           ruta_imagen=ruta_imagen)

@preguntas_bp.route("/timeout/<int:pregunta_id>")
def timeout(pregunta_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")

            # Grupo activo
            try:
                id_grupo = _get_id_grupo_activo(usuario_id)
            except RuntimeError:
                return redirect(url_for("index"))

            # Si ya respondió esta pregunta en este grupo, no duplicar
            cur.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario=? AND id_grupo=? AND id_pregunta=?
            """, (usuario_id, id_grupo, pregunta_id))
            if cur.fetchone():
                return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

            # Puntuación anterior (no sube en timeout)
            puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo)

            cur.execute("""
                INSERT INTO Resultados
                (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                usuario_id,
                id_grupo,
                "2025-T1",
                puntuacion_anterior,
                0,
                pregunta_id,
                0   # id_respuesta timeout (debes tenerlo creado)
            ))
            conn.commit()

    return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
