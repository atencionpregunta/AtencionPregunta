from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_conn, db_lock
from utils import get_grupos_usuario

# OJO: el nombre del blueprint debe ser "resultados" para que el endpoint sea resultados.ver_resultados
resultados_bp = Blueprint("resultados", __name__)

@resultados_bp.route("/resultados", methods=["GET"])
def ver_resultados():
    # Requiere login
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    # Debe pertenecer a ≥1 grupo
    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para ver resultados.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    # Lee id_grupo por query (?id_grupo=)
    id_grupo_req = request.args.get("id_grupo", type=int)
    ids_propios = {g["id"] for g in grupos}
    id_grupo = id_grupo_req if id_grupo_req in ids_propios else grupos[0]["id"]

    # Ranking = última fila de Resultados por usuario en ese grupo (puntuación acumulada)
    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                WITH ult AS (
                  SELECT id_usuario, MAX(datetime(fecha)) AS maxf
                  FROM Resultados
                  WHERE id_grupo = ?
                  GROUP BY id_usuario
                )
                SELECT R.id_usuario,
                       COALESCE(U.usuario, U.mail, 'Usuario ' || R.id_usuario) AS usuario,
                       R.puntuacion,
                       R.correcta,
                       R.fecha
                FROM Resultados R
                JOIN ult ON ult.id_usuario = R.id_usuario AND datetime(R.fecha) = ult.maxf
                JOIN Usuarios U ON U.id = R.id_usuario
                WHERE R.id_grupo = ?
                ORDER BY R.puntuacion DESC, R.fecha ASC, usuario ASC
            """, (id_grupo, id_grupo))
            rows = cur.fetchall()

    resultados = [
        dict(
            id_usuario=r["id_usuario"],
            usuario=r["usuario"],
            puntuacion=r["puntuacion"],
            correcta=r["correcta"],
            fecha=r["fecha"],
        )
        for r in rows
    ]

    return render_template(
        "resultado.html",
        grupos_usuario=grupos,   # para el <select>
        id_grupo=id_grupo,       # seleccionado
        resultados=resultados    # tu tabla
    )
