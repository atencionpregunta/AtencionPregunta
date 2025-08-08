from flask import render_template, session, redirect, url_for
from db import get_conn
from . import resultados_bp

@resultados_bp.route("/ver_resultados/<int:id_grupo>")
def ver_resultados(id_grupo):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.usuario, r.puntuacion, r.fecha
        FROM Resultados r
        JOIN Usuarios u ON r.id_usuario = u.id
        WHERE r.id_grupo = ?
        ORDER BY r.puntuacion DESC, r.fecha ASC
    """, (id_grupo,))
    resultados = cursor.fetchall()
    conn.close()

    return render_template("resultado.html", resultados=resultados)

@resultados_bp.route("/mis_resultados")
def mis_resultados():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login_form"))

    id_usuario = session["usuario_id"]

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.codigo AS nombre, p.pregunta AS texto, r.puntuacion, r.fecha
        FROM Resultados r
        JOIN Grupos g ON r.id_grupo = g.id
        JOIN Preguntas p ON r.id_pregunta = p.id
        WHERE r.id_usuario = ?
        ORDER BY r.fecha DESC
    """, (id_usuario,))
    mis_resultados = cursor.fetchall()
    conn.close()

    return render_template("resultado.html", resultados=mis_resultados)
