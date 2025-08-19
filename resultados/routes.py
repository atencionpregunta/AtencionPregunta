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
        SELECT u.id AS id_usuario, u.usuario, r1.puntuacion, r1.fecha, r1.correcta
        FROM Resultados r1
        JOIN Usuarios u ON u.id = r1.id_usuario
        WHERE r1.id_grupo = ?
        AND r1.rowid = (
            SELECT MAX(r2.rowid)
            FROM Resultados r2
            WHERE r2.id_grupo = r1.id_grupo
            AND r2.id_usuario = r1.id_usuario
            AND r2.fecha = (
                SELECT MAX(r3.fecha)
                FROM Resultados r3
                WHERE r3.id_grupo = r1.id_grupo
                AND r3.id_usuario = r1.id_usuario
            )
        )
        ORDER BY r1.puntuacion DESC, r1.fecha DESC, u.usuario ASC;
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
