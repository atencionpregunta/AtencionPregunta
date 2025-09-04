from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_conn, db_lock
from . import chat_bp

TZ = ZoneInfo("Europe/Madrid")

# ===================== Tiempo =====================
def ahora_local_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def hoy_local_str():
    return datetime.now(TZ).date().isoformat()  # 'YYYY-MM-DD'

# ===================== Util DB =====================
def _grupo_existe(conn, id_grupo: int) -> bool:
    row = conn.execute("SELECT 1 FROM Grupos WHERE id=?", (id_grupo,)).fetchone()
    return bool(row)

def _has_column(conn, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())

# ===================== Badges ======================
def _badges_por_usuario(conn, id_grupo: int) -> dict:
    """
    Lee de Resultados:
      - acierto (hoy): MAX(correcta) para date(fecha)=hoy
      - rank: orden por SUM(puntuacion) en el grupo
    Devuelve { id_usuario: {'acierto': True/False/None, 'rank': int|None} }
    """
    badges: dict[int, dict] = {}
    hoy = hoy_local_str()

    # ---- ACIERTO HOY ----
    # Usamos date(fecha)=? para que funcione aunque tenga hora
    filas = conn.execute(
        """
        SELECT id_usuario,
               MAX(CASE WHEN correcta=1 THEN 1 ELSE 0 END) AS acierto
        FROM Resultados
        WHERE id_grupo=? AND date(fecha)=?
        GROUP BY id_usuario
        """,
        (id_grupo, hoy),
    ).fetchall()
    for r in filas:
        badges.setdefault(r["id_usuario"], {})["acierto"] = bool(r["acierto"])

    # ---- RANK por puntos acumulados en el grupo ----
    puntos = conn.execute(
        """
        SELECT id_usuario, COALESCE(SUM(puntuacion),0) AS pts
        FROM Resultados
        WHERE id_grupo=?
        GROUP BY id_usuario
        ORDER BY pts DESC
        """,
        (id_grupo,),
    ).fetchall()

    # Asignamos rank (1,2,3...) gestionando empates
    rank = 0
    last_pts = None
    for idx, r in enumerate(puntos, start=1):
        if last_pts is None or r["pts"] != last_pts:
            rank = idx
            last_pts = r["pts"]
        badges.setdefault(r["id_usuario"], {})["rank"] = rank

    return badges

# ========================= Rutas ================================

# Vista principal del chat
@chat_bp.route("/grupos/<int:id_grupo>/chat")
def ver_chat(id_grupo):
    if "usuario_id" not in session:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("auth.login"))

    with db_lock, get_conn() as conn:
        if not _grupo_existe(conn, id_grupo):
            flash("Grupo no encontrado.", "error")
            return redirect(url_for("index"))

        # foto_url existe en tu esquema de Usuarios ✅
        sql = """
            SELECT M.id, M.id_usuario, M.contenido, M.created_at,
                   U.usuario AS usuario_nombre,
                   U.foto_url AS foto_url
            FROM Mensajes M
            LEFT JOIN Usuarios U ON U.id = M.id_usuario
            WHERE M.id_grupo = ?
            ORDER BY M.created_at DESC, M.id DESC
            LIMIT 100
        """
        mensajes = conn.execute(sql, (id_grupo,)).fetchall()

        badges = _badges_por_usuario(conn, id_grupo) or {}

    mensajes = list(reversed(mensajes))

    return render_template(
        "chat.html",
        id_grupo=id_grupo,
        mensajes=mensajes,
        badges=badges,
    )

# Endpoint JSON para polling
@chat_bp.route("/grupos/<int:id_grupo>/chat/mensajes")
def api_mensajes(id_grupo):
    if "usuario_id" not in session:
        return jsonify({"ok": False, "error": "no_auth"}), 401

    after_id = request.args.get("after_id", type=int)

    with db_lock, get_conn() as conn:
        base = """
            SELECT M.id, M.id_usuario, M.contenido, M.created_at,
                   COALESCE(U.usuario, '') AS usuario_nombre,
                   U.foto_url AS foto_url
            FROM Mensajes M
            LEFT JOIN Usuarios U ON U.id = M.id_usuario
            WHERE M.id_grupo = ?
        """
        params = [id_grupo]
        if after_id:
            base += " AND M.id > ?"
            params.append(after_id)
        base += " ORDER BY M.id ASC"

        filas = conn.execute(base, params).fetchall()
        badges = _badges_por_usuario(conn, id_grupo) or {}

    items = []
    for r in filas:
        b = badges.get(r["id_usuario"], {})
        items.append({
            "id": r["id"],
            "id_usuario": r["id_usuario"],
            "usuario_nombre": r["usuario_nombre"] or f"User {r['id_usuario']}",
            "foto_url": r["foto_url"],
            "contenido": r["contenido"],
            "created_at": r["created_at"],
            "acierto": b.get("acierto"),
            "rank": b.get("rank"),
        })

    return jsonify({"ok": True, "mensajes": items})

# Enviar mensaje
@chat_bp.route("/grupos/<int:id_grupo>/chat/enviar", methods=["POST"])
def enviar_mensaje(id_grupo):
    if "usuario_id" not in session:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("auth.login"))

    contenido = (request.form.get("contenido") or "").strip()
    if not contenido:
        return redirect(url_for("chat.ver_chat", id_grupo=id_grupo))

    with db_lock, get_conn() as conn:
        if not _grupo_existe(conn, id_grupo):
            flash("Grupo no encontrado.", "error")
            return redirect(url_for("index"))

        conn.execute("""
            INSERT INTO Mensajes (id_grupo, id_usuario, contenido, created_at)
            VALUES (?, ?, ?, ?)
        """, (id_grupo, session["usuario_id"], contenido, ahora_local_str()))
        conn.commit()

    return redirect(url_for("chat.ver_chat", id_grupo=id_grupo))
