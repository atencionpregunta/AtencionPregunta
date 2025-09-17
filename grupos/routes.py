from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import sqlite3
from db import get_conn, db_lock
from utils import get_grupos_usuario
from . import grupos_bp

# =========================
# Helpers existentes
# =========================

def codigo_existe(codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not codigo:
        return False
    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM Grupos WHERE LOWER(codigo) = LOWER(?) LIMIT 1", (codigo,))
            return cur.fetchone() is not None


@grupos_bp.route("/check_codigo")
def check_codigo():
    codigo = (request.args.get("codigo") or "").strip()
    if not codigo:
        return jsonify({"available": False})
    return jsonify({"available": not codigo_existe(codigo)})

# =========================
# Crear grupo
# =========================
@grupos_bp.route("/crear_grupo", methods=["GET", "POST"])
def crear_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    if request.method == "POST":
        nombre = (request.form.get("nombre_grupo") or "").strip()
        contrasena = (request.form.get("contrasena_grupo") or "").strip()
        tipo = (request.form.get("tipo_grupo") or "publico").strip().lower()
        raw_dur = (request.form.get("duracion_dias") or "").strip()  # ← ahora sí definido

        # Normaliza tipo
        if tipo not in ("publico", "privado"):
            tipo = "publico"

        # Validaciones básicas
        if not nombre:
            flash("Falta el nombre del grupo.", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        if codigo_existe(nombre):
            flash("Ya existe un grupo con ese nombre ❌", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        # Duración OBLIGATORIA (1..365)
        try:
            dur_temp = int(raw_dur)
            if not (1 <= dur_temp <= 365):
                raise ValueError()
        except ValueError:
            flash("La duración debe ser un número entre 1 y 365 días.", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        # (Opcional) si el grupo es privado, exige contraseña
        if tipo == "privado" and not contrasena:
            flash("Para grupos privados debes indicar una contraseña.", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        # Inserción en BD
        try:
            with db_lock, get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO Grupos (fec_ini, duracion_temp, codigo, tipo, contrasena)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        dur_temp,                    # entero validado
                        nombre,
                        tipo,
                        contrasena or None
                    )
                )
                grupo_id = cur.lastrowid

                cur.execute(
                    "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
                    (grupo_id, usuario_id)
                )
                conn.commit()

            session["grupo_actual"] = nombre
            flash(f"Grupo '{nombre}' creado correctamente ✅", "success")
            return redirect(url_for("grupos.gestionar_grupos"))

        except sqlite3.IntegrityError:
            # Doble defensa ante condiciones de carrera o índice único
            flash("Ya existe un grupo con ese nombre ❌", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

    # GET
    return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))


# =========================
# Unirse a grupo (form)
# =========================
@grupos_bp.route("/unirse_grupo", methods=["GET", "POST"])
def unirse_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    if request.method == "POST":
        codigo = (request.form.get("codigo_grupo") or "").strip()
        contrasena = (request.form.get("contrasena_grupo") or "").strip()

        if not codigo:
            flash("Falta el código del grupo.", "error")
            return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        with db_lock:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM Grupos WHERE LOWER(codigo) = LOWER(?)", (codigo,))
                grupo = cur.fetchone()

                if not grupo:
                    flash("Grupo no encontrado ❌", "error")
                    return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

                # ✅ Cálculo correcto sin usar .get() (sqlite3.Row)
                tipo_val = (grupo["tipo"] or "").strip().lower() if "tipo" in grupo.keys() else ""
                pwd_val  = (grupo["contrasena"] or "")
                is_priv  = bool(pwd_val) or (tipo_val == "privado")

                if is_priv and pwd_val != contrasena:
                    flash("Contraseña incorrecta ❌", "error")
                    return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

                cur.execute(
                    "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
                    (grupo["id"], usuario_id)
                )
                conn.commit()

        session["grupo_actual"] = grupo["codigo"]
        flash(f"Te has unido al grupo '{grupo['codigo']}' 🎉", "success")
        return redirect(url_for("grupos.gestionar_grupos"))

    # GET
    return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

# =========================
# Gestionar / Salir
# =========================
@grupos_bp.route("/gestionar", methods=["GET"])
def gestionar_grupos():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    grupos = get_grupos_usuario(usuario_id)
    return render_template("gestionar_grupos.html", grupos_usuario=grupos)


@grupos_bp.route("/salir_grupo", methods=["POST"])
def salir_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    id_grupo = request.form.get("id_grupo", type=int)
    if not id_grupo:
        flash("Grupo inválido.", "error")
        return redirect(url_for("grupos.gestionar_grupos"))

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT G.id, G.codigo
                FROM Grupos G
                JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
                WHERE GU.id_usuario = ? AND G.id = ?
            """, (usuario_id, id_grupo))
            row = cur.fetchone()
            if not row:
                flash("No perteneces a ese grupo.", "error")
                return redirect(url_for("grupos.gestionar_grupos"))

            cur.execute("SELECT COUNT(*) FROM Grupo_Usuario WHERE id_usuario = ?", (usuario_id,))
            total = cur.fetchone()[0]
            if total <= 1:
                flash("No puedes salirte de tu único grupo. Únete a otro antes.", "warning")
                return redirect(url_for("grupos.gestionar_grupos"))

            cur.execute(
                "DELETE FROM Grupo_Usuario WHERE id_usuario = ? AND id_grupo = ?",
                (usuario_id, id_grupo)
            )
            conn.commit()

            if session.get("grupo_actual") == row["codigo"]:
                cur.execute("""
                    SELECT G.codigo
                    FROM Grupos G
                    JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
                    WHERE GU.id_usuario = ?
                    ORDER BY G.codigo
                    LIMIT 1
                """, (usuario_id,))
                nuevo = cur.fetchone()
                session["grupo_actual"] = nuevo["codigo"] if nuevo else None

    flash("Has salido del grupo correctamente.", "success")
    return redirect(url_for("grupos.gestionar_grupos"))

# =========================
# Listar públicos (existente)
# =========================
@grupos_bp.route("/publicos")
def listar_publicos():
    q = (request.args.get("q") or "").strip().lower()
    limit = request.args.get("limit", type=int) or 25
    offset = request.args.get("offset", type=int) or 0
    usuario_id = session.get("usuario_id")

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            params = []
            sql = """
                SELECT g.id, g.codigo, COUNT(gu.id_usuario) AS miembros
                FROM Grupos g
                LEFT JOIN Grupo_Usuario gu ON gu.id_grupo = g.id
                WHERE g.tipo='publico'
            """
            if usuario_id:
                sql += " AND g.id NOT IN (SELECT id_grupo FROM Grupo_Usuario WHERE id_usuario = ?)"
                params.append(usuario_id)

            if q:
                sql += " AND LOWER(g.codigo) LIKE ?"
                params.append(f"%{q}%")

            sql += " GROUP BY g.id, g.codigo ORDER BY g.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(sql, params)
            rows = cur.fetchall()

    items = [{"id": r["id"], "codigo": r["codigo"], "miembros": r["miembros"]} for r in rows]
    return jsonify({"items": items, "limit": limit, "offset": offset})

@grupos_bp.get("/grupos/check-nombre")
def check_nombre():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"exists": False})
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM Grupos WHERE codigo = ? COLLATE NOCASE", (q,))
        return jsonify({"exists": cur.fetchone() is not None})

# ============================================================
# 🔥 NUEVO: /grupos/buscar — públicos + privados con filtros
# ============================================================
@grupos_bp.route("/buscar")
def buscar_grupos():
    """
    Lista grupos disponibles (EXCLUYE los que ya pertenece el usuario).
    Respuesta con progreso (días transcurridos/restantes) y flags de privacidad.
    """
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"items": [], "limit": 25, "offset": 0})

    q      = (request.args.get("q") or "").strip().lower()
    tipo   = (request.args.get("tipo") or "").strip().lower()
    sort   = (request.args.get("sort") or "miembros_desc").strip().lower()
    limit  = request.args.get("limit", type=int) or 25
    offset = request.args.get("offset", type=int) or 0

    order_sql = {
        "miembros_desc": "miembros DESC, g.id DESC",
        "miembros_asc":  "miembros ASC, g.id DESC",
        "duracion_asc":  "CASE WHEN g.duracion_temp IS NULL THEN 999999 ELSE g.duracion_temp END ASC, g.id DESC",
        "duracion_desc": "CASE WHEN g.duracion_temp IS NULL THEN -1 ELSE g.duracion_temp END DESC, g.id DESC",
    }.get(sort, "miembros DESC, g.id DESC")

    params = []
    where = ["1=1"]

    # ❌ EXCLUIR grupos donde ya está el usuario
    where.append("g.id NOT IN (SELECT id_grupo FROM Grupo_Usuario WHERE id_usuario = ?)")
    params.append(usuario_id)

    if q:
        where.append("LOWER(g.codigo) LIKE ?")
        params.append(f"%{q}%")

    if tipo in ("publico", "privado"):
        where.append("LOWER(g.tipo) = ?")
        params.append(tipo)

    sql = f"""
        SELECT
            g.id,
            g.codigo,
            LOWER(COALESCE(g.tipo, 'publico')) AS tipo,
            COUNT(gu.id_usuario) AS miembros,
            g.duracion_temp AS duracion_dias,
            g.fec_ini AS fec_ini,
            CASE
              WHEN (g.contrasena IS NOT NULL AND g.contrasena <> '') OR LOWER(COALESCE(g.tipo,'')) = 'privado'
              THEN 1 ELSE 0
            END AS requiere_password
        FROM Grupos g
        LEFT JOIN Grupo_Usuario gu ON gu.id_grupo = g.id
        WHERE {" AND ".join(where)}
        GROUP BY g.id, g.codigo, tipo, g.duracion_temp, g.contrasena, g.fec_ini
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    # ---- Cálculos de progreso ----
    def _parse_dt(s):
        if not s: return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        return None

    now = datetime.now()
    items = []
    for r in rows:
        dur = r["duracion_dias"]  # None => ∞
        start = _parse_dt(r["fec_ini"])
        dias_trans = max(0, (now - start).days) if start else 0

        if dur is None:
            dias_rest = None
            pct = None
            etiqueta = f"{dias_trans} d · ∞"
            estado = "ongoing"
        else:
            tot = max(1, int(dur))
            dias_rest = max(0, tot - dias_trans)
            pct = min(100, int(round(min(dias_trans, tot) * 100 / tot)))
            etiqueta = f"{min(dias_trans, tot)}/{tot} d"
            estado = "done" if dias_rest == 0 else "active"

        items.append({
            "id": r["id"],
            "codigo": r["codigo"],
            "tipo": r["tipo"] or "publico",
            "miembros": r["miembros"] or 0,
            "duracion_dias": r["duracion_dias"],
            "requiere_password": bool(r["requiere_password"]),
            "fec_ini": r["fec_ini"],
            "dias_transcurridos": dias_trans,
            "dias_restantes": dias_rest,
            "progreso_pct": pct,
            "progreso_label": etiqueta,
            "estado_temp": estado,
        })

    return jsonify({"items": items, "limit": limit, "offset": offset})

# ============================================================
# (Opcional) Unirse por API (JSON) para futuros usos
# ============================================================
@grupos_bp.route("/unirse_api", methods=["POST"])
def unirse_api():
    """
    JSON: {"codigo": "...", "contrasena": "..." }
    """
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    data = request.get_json(silent=True) or {}
    codigo = (data.get("codigo") or "").strip()
    contrasena = (data.get("contrasena") or "").strip()

    if not codigo:
        return jsonify({"ok": False, "error": "missing_code"}), 400

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM Grupos WHERE LOWER(codigo) = LOWER(?)", (codigo,))
            grupo = cur.fetchone()
            if not grupo:
                return jsonify({"ok": False, "error": "not_found"}), 404

            # ✅ Cálculo correcto sin .get()
            tipo_val = (grupo["tipo"] or "").strip().lower() if "tipo" in grupo.keys() else ""
            pwd_val  = (grupo["contrasena"] or "")
            is_priv  = bool(pwd_val) or (tipo_val == "privado")

            if is_priv and pwd_val != contrasena:
                return jsonify({"ok": False, "error": "bad_password"}), 403

            cur.execute(
                "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
                (grupo["id"], usuario_id)
            )
            conn.commit()

    session["grupo_actual"] = grupo["codigo"]
    return jsonify({"ok": True, "grupo": {"id": grupo["id"], "codigo": grupo["codigo"]}})
