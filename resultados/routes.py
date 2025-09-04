from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_conn, db_lock
from utils import get_grupos_usuario
from datetime import datetime
from zoneinfo import ZoneInfo

# OJO: el nombre del blueprint debe ser "resultados" para que el endpoint sea resultados.ver_resultados
resultados_bp = Blueprint("resultados", __name__)

TZ = ZoneInfo("Europe/Madrid")

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

    # Lee id_grupo (?id_grupo=) y valida pertenencia
    id_grupo_req = request.args.get("id_grupo", type=int)
    ids_propios = {g["id"] for g in grupos}
    id_grupo = id_grupo_req if id_grupo_req in ids_propios else grupos[0]["id"]

    with db_lock, get_conn() as conn:
        cur = conn.cursor()

        # 1) Pregunta actual = la de fecha_mostrada más reciente (si existe)
        cur.execute("""
            SELECT id
            FROM Preguntas
            WHERE fecha_mostrada IS NOT NULL
            ORDER BY datetime(fecha_mostrada) DESC, id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        id_pregunta_actual = row["id"] if row else None

        # Fallback: si no hay fecha_mostrada, usa la última pregunta usada en Resultados del grupo
        if id_pregunta_actual is None:
            cur.execute("""
                SELECT id_pregunta
                FROM Resultados
                WHERE id_grupo = ?
                ORDER BY datetime(fecha) DESC
                LIMIT 1
            """, (id_grupo,))
            r2 = cur.fetchone()
            id_pregunta_actual = r2["id_pregunta"] if r2 else None

        resultados = []
        if id_pregunta_actual is not None:
            # 2) Estado por usuario para ESA pregunta (incluye a todos los miembros del grupo)
            cur.execute("""
                WITH estado AS (
                  SELECT
                    id_usuario,
                    SUM(COALESCE(puntuacion,0))                                AS puntos_preg,
                    MAX(CASE WHEN correcta = 1 THEN 1 ELSE 0 END)              AS correcta_flag
                  FROM Resultados
                  WHERE id_grupo = ? AND id_pregunta = ?
                  GROUP BY id_usuario
                )
                SELECT
                  U.id                                                       AS id_usuario,
                  COALESCE(U.usuario, U.mail, 'Usuario ' || U.id)            AS usuario,
                  COALESCE(e.puntos_preg, 0)                                 AS puntuacion,
                  e.correcta_flag                                            AS correcta
                FROM grupo_usuario GU
                JOIN Usuarios U ON U.id = GU.id_usuario
                LEFT JOIN estado e  ON e.id_usuario = U.id
                WHERE GU.id_grupo = ?
                ORDER BY COALESCE(e.puntos_preg, 0) DESC,
                         U.usuario COLLATE NOCASE ASC
            """, (id_grupo, id_pregunta_actual, id_grupo))
            rows = cur.fetchall()

            resultados = [
                {
                    "id_usuario": r["id_usuario"],
                    "usuario": r["usuario"],
                    "puntuacion": r["puntuacion"],   # puntos en la PREGUNTA ACTUAL
                    "correcta": r["correcta"],       # 1/0 o None si no ha respondido la actual
                }
                for r in rows
            ]
        else:
            # No hay pregunta actual detectable → lista miembros del grupo con 0/None
            cur.execute("""
                SELECT U.id AS id_usuario,
                       COALESCE(U.usuario, U.mail, 'Usuario ' || U.id) AS usuario
                FROM grupo_usuario GU
                JOIN Usuarios U ON U.id = GU.id_usuario
                WHERE GU.id_grupo = ?
                ORDER BY U.usuario COLLATE NOCASE ASC
            """, (id_grupo,))
            rows = cur.fetchall()
            resultados = [
                {"id_usuario": r["id_usuario"], "usuario": r["usuario"], "puntuacion": 0, "correcta": None}
                for r in rows
            ]

    return render_template(
        "resultado.html",
        grupos_usuario=grupos,   # para el <select>
        id_grupo=id_grupo,       # seleccionado
        resultados=resultados    # tu tabla (usa r.correcta / r.puntuacion como ya tienes)
    )
