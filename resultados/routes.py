from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_conn, db_lock
from utils import get_grupos_usuario, dias_temporada_restantes, ensure_active_temporada,jornada_bounds, ahora_local
from datetime import datetime, date
from zoneinfo import ZoneInfo
import sqlite3

# OJO: el nombre del blueprint debe ser "resultados" para que el endpoint sea resultados.ver_resultados
resultados_bp = Blueprint("resultados", __name__)

TZ = ZoneInfo("Europe/Madrid")

@resultados_bp.route("/historial", methods=["GET"])
def historial_temporadas():
    # --- Helpers internos ---
    def _grupo_id(g):
        for k in ("id", "id_grupo", "grupo_id"):
            if k in g and g[k] is not None:
                return int(g[k])
        return None

    def _grupo_nombre(g):
        # tu esquema no tiene columna "nombre" en Grupos; usamos "codigo"
        if "codigo" in g and g["codigo"]:
            return str(g["codigo"])
        gid = _grupo_id(g)
        return f"Grupo {gid}" if gid is not None else "Grupo"

    # --- Requiere login ---
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    # --- Debe pertenecer a ≥1 grupo ---
    grupos = get_grupos_usuario(usuario_id)
    if not grupos:
        flash("Debes unirte a un grupo para ver el historial.", "error")
        return redirect(url_for("grupos.unirse_grupo"))

    # --- id_grupo & id_temporada (query) ---
    try:
        id_grupo = int(request.args.get("id_grupo") or "0")
    except ValueError:
        id_grupo = 0
    id_temporada_q = (request.args.get("id_temporada") or "").strip()  # "", "all" o un id

    grupo_ids = {_grupo_id(g) for g in grupos if _grupo_id(g) is not None}
    if not id_grupo or id_grupo not in grupo_ids:
        id_grupo = next((_grupo_id(g) for g in grupos if _grupo_id(g) is not None), 0)

    # Nombre del grupo directo desde BD (en tu esquema es "codigo")
    with db_lock, get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COALESCE(codigo, 'Grupo ' || ?) AS nombre
            FROM Grupos
            WHERE id = ?
        """, (id_grupo, id_grupo))
        row_ng = c.fetchone()
        nombre_grupo = (row_ng["nombre"] if row_ng else f"Grupo {id_grupo}")

    # Garantiza temporada activa (si tu helper crea una si no existe)
    try:
        ensure_active_temporada(id_grupo)
    except Exception:
        pass

    temporadas = []
    clasif_por_temp = {}

    with db_lock, get_conn() as conn:
        c = conn.cursor()

        # 1) Traer temporadas del grupo (cerradas y abiertas)
        c.execute("""
            SELECT id, nombre, fecha_inicio, fecha_fin, duracion_dias, activa
            FROM Temporadas
            WHERE id_grupo = ?
            ORDER BY date(fecha_inicio) DESC, id DESC
        """, (id_grupo,))
        raw_temps = c.fetchall()

        temporadas = [{
            "id": row["id"],
            "nombre": row["nombre"],
            "fecha_inicio": row["fecha_inicio"],
            "fecha_fin": row["fecha_fin"],
            "duracion_dias": row["duracion_dias"],
            "activa": row["activa"],
        } for row in raw_temps]

        # Fallback: si NO hay temporadas pero sí hay Resultados → temporada virtual
        if not temporadas:
            c.execute("""
                SELECT MIN(date(r.fecha)) AS ini,
                       MAX(date(r.fecha)) AS fin,
                       COUNT(*) AS n
                FROM Resultados r
                WHERE r.id_grupo = ?
            """, (id_grupo,))
            rng_row = c.fetchone()
            rng = dict(rng_row) if rng_row else {}
            if (rng.get("n") or 0) > 0:
                temporadas = [{
                    "id": 0,                       # id virtual SOLO para UI
                    "nombre": "Temporada actual", # opcional
                    "fecha_inicio": rng.get("ini"),
                    "fecha_fin": None,
                    "duracion_dias": None,
                    "activa": 1,
                }]

        # Normalizar selección desde query
        if id_temporada_q and id_temporada_q != "all":
            try:
                sel_id = int(id_temporada_q)
            except ValueError:
                sel_id = None
        else:
            sel_id = None  # "all" o vacío

        # 2) Construir meta + ranking para cada temporada seleccionada
        def _build_for_temp(t: dict):
            """
            Intenta emparejar Resultados.temporada por ID (texto/num) o por nombre.
            Si no hay valor, usa el rango de fechas de la temporada.
            """
            tid   = str(t.get("id")) if t and t.get("id") is not None else None  # id como texto
            tname = (t.get("nombre") or "").strip() or None
            f_ini = t.get("fecha_inicio")
            f_fin = t.get("fecha_fin")

            # META
            c.execute("""
                SELECT 
                    MIN(date(r.fecha)) AS primera,
                    MAX(date(r.fecha)) AS ultima,
                    COUNT(DISTINCT r.id_pregunta) AS num_pregs
                FROM Resultados r
                WHERE r.id_grupo = ?
                  AND (
                        ( ? IS NOT NULL AND r.temporada = ? )                             -- por ID
                     OR ( ? IS NOT NULL AND ? != '' AND r.temporada = ? )                 -- por nombre
                     OR ( date(r.fecha) BETWEEN date(?) AND date(COALESCE(?, '9999-12-31')) ) -- por fechas
                  )
            """, (
                id_grupo,
                tid, tid,
                tname, tname, tname,
                f_ini, f_fin
            ))
            meta_row = c.fetchone()
            meta = dict(meta_row) if meta_row else {}
            t["primera"]   = meta.get("primera")
            t["ultima"]    = meta.get("ultima")
            t["num_pregs"] = int(meta.get("num_pregs") or 0)

            # RANKING
            c.execute("""
                SELECT u.id AS id_usuario,
                       COALESCE(u.usuario, 'Usuario ' || u.id) AS nombre,
                       SUM(COALESCE(r.puntuacion,0)) AS puntos,
                       SUM(CASE WHEN r.correcta=1 THEN 1 ELSE 0 END) AS aciertos,
                       COUNT(*) AS jugadas
                FROM Resultados r
                JOIN Usuarios u ON u.id = r.id_usuario
                WHERE r.id_grupo = ?
                  AND (
                        ( ? IS NOT NULL AND r.temporada = ? )                             -- por ID
                     OR ( ? IS NOT NULL AND ? != '' AND r.temporada = ? )                 -- por nombre
                     OR ( date(r.fecha) BETWEEN date(?) AND date(COALESCE(?, '9999-12-31')) ) -- por fechas
                  )
                GROUP BY u.id, u.usuario
                HAVING jugadas > 0
                ORDER BY puntos DESC, aciertos DESC, jugadas DESC, nombre ASC
            """, (
                id_grupo,
                tid, tid,
                tname, tname, tname,
                f_ini, f_fin
            ))
            rows = c.fetchall()

            lista, rank = [], 1
            for r in rows:
                lista.append({
                    "id_usuario": r["id_usuario"],
                    "nombre": r["nombre"],
                    "puntos": int(r["puntos"] or 0),
                    "aciertos": int(r["aciertos"] or 0),
                    "jugadas": int(r["jugadas"] or 0),
                    "rank": rank
                })
                rank += 1
            return lista

        clasif_por_temp = {}
        if temporadas:
            if id_temporada_q == "all":
                for t in temporadas:
                    clasif_por_temp[str(t["id"])] = _build_for_temp(t)
                selected_temporada = "all"
            else:
                if sel_id is None:
                    t_sel = temporadas[0]
                else:
                    t_sel = next((t for t in temporadas if t["id"] == sel_id), None) or temporadas[0]
                clasif_por_temp[str(t_sel["id"])] = _build_for_temp(t_sel)
                selected_temporada = str(t_sel["id"])
        else:
            selected_temporada = ""

    # Normaliza claves a string (defensivo para Alpine)
    clasif_por_temp = {str(k): v for k, v in clasif_por_temp.items()}

    # DEBUG
    print("DBG /historial -> id_grupo:", id_grupo,
          "| nombre_grupo:", nombre_grupo,
          "| temporadas:", len(temporadas),
          "| selected:", selected_temporada)

    # Render
    return render_template(
        "historial_temporadas.html",
        id_grupo=id_grupo,
        grupos=grupos,
        nombre_grupo=nombre_grupo,
        temporadas=temporadas,
        clasif_por_temp=clasif_por_temp,
        selected_temporada=selected_temporada
    )




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

        # 1) Buscar la temporada anterior
        dia_eff = date.fromisoformat(jornada_bounds()[2])  # tu día efectivo
        _cur.execute("""
            SELECT id
            FROM Temporadas
            WHERE id_grupo=? AND date(fecha_fin) < ?
            ORDER BY date(fecha_fin) DESC
            LIMIT 1
        """, (id_grupo, dia_eff))
        t_prev = _cur.fetchone()

        campeon_id = None
        if t_prev:
            # 2) Sumar puntos y elegir top-1 de esa temporada
            _cur.execute("""
            SELECT r.id_usuario, SUM(r.puntuacion) AS pts
            FROM Resultados r
            WHERE r.id_grupo=? AND r.id_temporada=?
            GROUP BY r.id_usuario
            ORDER BY pts DESC, r.id_usuario ASC
            LIMIT 1
            """, (id_grupo, t_prev["id"]))
            row = _cur.fetchone()
            if row:
                campeon_id = row["id_usuario"]
            

    return render_template(
        "resultado.html",        # (asegúrate de usar el nombre correcto de tu plantilla)
        grupos_usuario=grupos,    # para sidebar / select
        id_grupo=id_grupo,        # seleccionado
        resultados=resultados,    # filas: r.puntuacion (acumulado), r.correcta (momento)
        nombre_temp = temporada_nombre,
        dias_restantes=dias_restantes,
        campeon_id = campeon_id,
        max_p=max_p
    )

