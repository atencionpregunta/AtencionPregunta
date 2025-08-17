from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from db import get_conn, db_lock
from utils import (
    get_puntuacion_anterior,
    get_pregunta_del_dia,
    get_cod_grupo_actual,
    get_id_grupo_actual,
)

preguntas_bp = Blueprint("preguntas", __name__)

@preguntas_bp.route("/ver_pregunta", methods=["GET", "POST"])
def ver_pregunta():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]

    if request.method == "POST":
        id_respuesta = request.form.get("respuesta")
        if not id_respuesta:
            flash("No se ha seleccionado una respuesta.", "warning")
            return redirect(url_for("preguntas.ver_pregunta"))

        # Resolver grupo obligatorio (según comentaste)
        id_grupo = get_id_grupo_actual(usuario_id)
        if not id_grupo:
            # intenta coger por código si lo tienes en sesión
            cod = session.get("grupo_actual") or get_cod_grupo_actual(usuario_id)
            if cod:
                with db_lock, get_conn() as conn:
                    c = conn.cursor()
                    c.execute("SELECT id FROM Grupos WHERE codigo = ?", (cod,))
                    row = c.fetchone()
                    id_grupo = row["id"] if row else None
            if not id_grupo:
                flash("Debes unirte a un grupo antes de responder.", "error")
                return redirect(url_for("index"))

        with db_lock, get_conn() as conn:
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")

            # 1) Cargar respuesta y pregunta_id
            c.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
            respuesta = c.fetchone()
            if not respuesta:
                flash("Respuesta no encontrada.", "error")
                return redirect(url_for("preguntas.ver_pregunta"))

            pregunta_id = respuesta["id_pregunta"]

            # 2) ¿Ya respondió esta PREGUNTA (independiente del grupo)?
            c.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND id_pregunta = ?
                LIMIT 1
            """, (usuario_id, pregunta_id))
            if c.fetchone():
                flash("Ya has respondido a la pregunta de hoy.", "warning")
                return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

            # 3) Puntuación anterior por grupo
            puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo) or 0

            # 4) Calcular y guardar
            correcta = int(respuesta["correcta"])
            nueva_puntuacion = puntuacion_anterior + 1 if correcta else puntuacion_anterior

            c.execute("""
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
                pregunta_id,
                respuesta["id"]
            ))
            conn.commit()

        return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

    # -- GET: mostrar pregunta del día
    pregunta_actual, respuestas = get_pregunta_del_dia()
    if not pregunta_actual:
        flash("No se ha podido cargar la pregunta del día.", "error")
        return redirect(url_for("index"))

    # cargar audio/imagen de la pregunta
    try:
        pregunta_id = pregunta_actual["id"]
    except Exception:
        pregunta_id = pregunta_actual.id

    with db_lock, get_conn() as conn:
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
    """Marca la pregunta como INCORRECTA por tiempo agotado (id_respuesta = 0) y redirige a resultados o index."""
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    usuario_id = session["usuario_id"]

    # Resolver grupo (obligatorio en tu app)
    id_grupo = get_id_grupo_actual(usuario_id)
    if not id_grupo:
        cod = session.get("grupo_actual") or get_cod_grupo_actual(usuario_id)
        if cod:
            with db_lock, get_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM Grupos WHERE codigo = ?", (cod,))
                row = c.fetchone()
                id_grupo = row["id"] if row else None
    if not id_grupo:
        # Si no hay grupo, no insertamos; simplemente volvemos
        flash("Debes unirte a un grupo antes de jugar.", "error")
        return redirect(url_for("index"))

    with db_lock, get_conn() as conn:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")

        # ¿Ya respondió esta PREGUNTA? (evitar duplicados de timeout)
        c.execute("""
            SELECT 1 FROM Resultados
            WHERE id_usuario = ? AND id_pregunta = ?
            LIMIT 1
        """, (usuario_id, pregunta_id))
        if c.fetchone():
            return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))

        # Puntuación anterior por grupo (no aumenta en timeout)
        puntuacion_anterior = get_puntuacion_anterior(usuario_id, id_grupo) or 0

        # Insertar como incorrecta con id_respuesta=0 (reservado en tu init_db)
        c.execute("""
            INSERT INTO Resultados
            (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            usuario_id,
            id_grupo,
            "2025-T1",
            puntuacion_anterior,
            0,              # incorrecta
            pregunta_id,
            0               # TIMEOUT
        ))
        conn.commit()

    return redirect(url_for("resultados.ver_resultados", id_grupo=id_grupo))
