from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_conn, db_lock
from utils import get_grupos_usuario, dias_temporada_restantes, ensure_active_temporada
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

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
    id_temp = ensure_active_temporada(id_grupo)

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1) Pregunta del momento = última con fecha_mostrada (si existe)
        cur.execute("""
            SELECT id
            FROM Preguntas
            WHERE fecha_mostrada IS NOT NULL
            ORDER BY datetime(fecha_mostrada) DESC, id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        id_pregunta_momento = row["id"] if row else None

        # Fallback: si no hay fecha_mostrada → última usada en Resultados del grupo
        if id_pregunta_momento is None:
            cur.execute("""
                SELECT id_pregunta
                FROM Resultados
                WHERE id_grupo = ?
                ORDER BY datetime(fecha) DESC, id_pregunta DESC
                LIMIT 1
            """, (id_grupo,))
            r2 = cur.fetchone()
            id_pregunta_momento = r2["id_pregunta"] if r2 else None

        resultados = []
        if id_pregunta_momento is not None:
            # 2) Miembros del grupo + acumulado histórico (por grupo) + estado en la PREGUNTA DEL MOMENTO
            cur.execute("""
                WITH miembros AS (
                  SELECT GU.id_usuario, COALESCE(U.usuario, U.mail, 'Usuario ' || U.id) AS usuario
                  FROM grupo_usuario GU
                  JOIN Usuarios U ON U.id = GU.id_usuario
                  WHERE GU.id_grupo = :id_grupo
                ),
                acum AS (
                  SELECT r.id_usuario,
                         SUM(CASE WHEN r.correcta = 1 THEN 1 ELSE 0 END)       AS aciertos_tot,
                         SUM(COALESCE(r.puntuacion, 0))                         AS puntos_tot
                  FROM Resultados r
                  WHERE r.id_grupo = :id_grupo and r.temporada = :id_temp
                  GROUP BY r.id_usuario
                ),
                momento AS (
                  SELECT r.id_usuario,
                         MAX(CASE WHEN r.correcta = 1 THEN 1 ELSE 0 END)        AS correcta_momento,
                         SUM(COALESCE(r.puntuacion, 0))                          AS puntos_momento
                  FROM Resultados r
                  WHERE r.id_grupo = :id_grupo AND r.id_pregunta = :id_pregunta_momento and r.temporada = :id_temp
                  GROUP BY r.id_usuario
                )
                SELECT  m.id_usuario,
                        m.usuario,
                        COALESCE(a.aciertos_tot, 0)    AS aciertos_tot,     -- acumulado por aciertos
                        COALESCE(a.puntos_tot, 0)      AS puntos_tot,       -- acumulado por puntos
                        COALESCE(mo.puntos_momento,0)  AS puntos_momento,   -- puntos en la pregunta del momento
                        mo.correcta_momento            AS correcta_momento  -- 1/0/NULL (colores)
                FROM miembros m
                LEFT JOIN acum a    ON a.id_usuario  = m.id_usuario
                LEFT JOIN momento mo ON mo.id_usuario = m.id_usuario
                ORDER BY aciertos_tot DESC, m.usuario COLLATE NOCASE ASC
            """, {"id_grupo": id_grupo, "id_pregunta_momento": id_pregunta_momento, "id_temp" : id_temp})
            rows = cur.fetchall()

            # ⚠️ Por defecto usamos ACERTADOS acumulados como 'puntuacion' (ranking).
            # Si prefieres puntos acumulados, cambia a r["puntos_tot"] y ajusta el ORDER BY de arriba.
            resultados = [
                {
                    "id_usuario": r["id_usuario"],
                    "usuario": r["usuario"],
                    "puntuacion": r["aciertos_tot"],          # ← acumulado: aciertos totales
                    "puntos_tot": r["puntos_tot"],            # (por si lo usas)
                    "puntos_momento": r["puntos_momento"],    # puntos SOLO en la pregunta del momento
                    "correcta": r["correcta_momento"],        # ← colores por pregunta del momento
                }
                for r in rows
            ]
        else:
            # No hay pregunta del momento detectable → lista miembros con acumulado y sin color
            cur.execute("""
                WITH miembros AS (
                  SELECT GU.id_usuario, COALESCE(U.usuario, U.mail, 'Usuario ' || U.id) AS usuario
                  FROM grupo_usuario GU
                  JOIN Usuarios U ON U.id = GU.id_usuario
                  WHERE GU.id_grupo = :id_grupo
                ),
                acum AS (
                  SELECT r.id_usuario,
                         SUM(CASE WHEN r.correcta = 1 THEN 1 ELSE 0 END) AS aciertos_tot,
                         SUM(COALESCE(r.puntuacion, 0))                   AS puntos_tot
                  FROM Resultados r
                  WHERE r.id_grupo = :id_grupo and r.temporada = :id_temp
                  GROUP BY r.id_usuario
                )
                SELECT m.id_usuario, m.usuario,
                       COALESCE(a.aciertos_tot, 0) AS aciertos_tot,
                       COALESCE(a.puntos_tot, 0)   AS puntos_tot
                FROM miembros m
                LEFT JOIN acum a ON a.id_usuario = m.id_usuario
                ORDER BY aciertos_tot DESC, m.usuario COLLATE NOCASE ASC
            """, {"id_grupo": id_grupo})
            rows = cur.fetchall()
            resultados = [
                {
                    "id_usuario": r["id_usuario"],
                    "usuario": r["usuario"],
                    "puntuacion": r["aciertos_tot"],   # acumulado
                    "puntos_tot": r["puntos_tot"],
                    "puntos_momento": 0,
                    "correcta": None                   # sin pregunta del momento → sin color
                }
                for r in rows
            ]

    # max_p para la barra (evita división por 0)
    max_p = max((r["puntuacion"] or 0) for r in resultados) if resultados else 1
    if max_p == 0:
        max_p = 1

    dias_restantes = dias_temporada_restantes(id_grupo)

    temp_id = ensure_active_temporada(id_grupo)  # fuera del db_lock para evitar bloqueos
    with get_conn() as _c:
        _cur = _c.cursor()
        row_t = _cur.execute("SELECT nombre FROM Temporadas WHERE id=?", (temp_id,)).fetchone()
        print(row_t["nombre"])
        temporada_nombre = row_t["nombre"] if row_t and row_t["nombre"] else str(temp_id)

    return render_template(
        "resultado.html",        # (asegúrate de usar el nombre correcto de tu plantilla)
        grupos_usuario=grupos,    # para sidebar / select
        id_grupo=id_grupo,        # seleccionado
        resultados=resultados,    # filas: r.puntuacion (acumulado), r.correcta (momento)
        nombre_temp = temporada_nombre,
        dias_restantes=dias_restantes,
        max_p=max_p
    )
