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
        SELECT u.id AS id_usuario, u.usuario, r.puntuacion, r.fecha, r.correcta
        FROM Resultados r
        JOIN Usuarios u ON r.id_usuario = u.id
        WHERE r.id_grupo = ?
        AND NOT EXISTS (
            SELECT 1
            FROM Resultados r2
            WHERE r2.id_grupo   = r.id_grupo
            AND r2.id_usuario = r.id_usuario
            AND (
                r2.fecha > r.fecha
                OR (r2.fecha = r.fecha AND r2.id > r.id)
            )
        )
        ORDER BY r.puntuacion DESC, r.fecha DESC, u.usuario ASC
        """, (id_grupo,))
    resultados = cursor.fetchall()
    conn.close()

    return render_template("resultado.html", resultados=resultados, usuario_id=session["usuario_id"])


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

    return render_template("resultado.html", resultados=mis_resultados, usuario_id=id_usuario)
