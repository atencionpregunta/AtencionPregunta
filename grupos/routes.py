from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import sqlite3
from db import get_conn, db_lock
from utils import get_grupos_usuario
from . import grupos_bp


def codigo_existe(codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not codigo:
        return False
    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            # Comparación case-insensitive segura en SQLite
            cur.execute("SELECT 1 FROM Grupos WHERE LOWER(codigo) = LOWER(?) LIMIT 1", (codigo,))
            return cur.fetchone() is not None


@grupos_bp.route("/check_codigo")
def check_codigo():
    """
    Endpoint AJAX: devuelve {"available": true/false}
    """
    codigo = (request.args.get("codigo") or "").strip()
    if not codigo:
        return jsonify({"available": False})
    return jsonify({"available": not codigo_existe(codigo)})


@grupos_bp.route("/crear_grupo", methods=["GET", "POST"])
def crear_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    if request.method == "POST":
        nombre = (request.form.get("nombre_grupo") or "").strip()
        contrasena = (request.form.get("contrasena_grupo") or "").strip()
        tipo = (request.form.get("tipo_grupo") or "publico").strip().lower()
        if request.form.get("duracion_dias"):
            dur_temp = request.form.get("duracion_dias") or None
        else:
            dur_temp = None


        if tipo not in ("publico", "privado"):
            tipo = "publico"
        
        if not nombre:
            flash("Falta el nombre del grupo.", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        if codigo_existe(nombre):
            flash("Ya existe un grupo con ese nombre ❌", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

        try:
            with db_lock:
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO Grupos (fec_ini, duracion_temp, codigo, tipo, contrasena) VALUES (?, ?, ?, ?, ?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dur_temp, nombre, tipo, contrasena or None)
                    )
                    grupo_id = cur.lastrowid
                    cur.execute(
                        "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
                        (grupo_id, usuario_id)
                    )
                    conn.commit()

            session["grupo_actual"] = nombre  # guardamos el código como activo (opcional)
            flash(f"Grupo '{nombre}' creado correctamente ✅", "success")
            return redirect(url_for("grupos.gestionar_grupos"))

        except sqlite3.IntegrityError:
            flash("Ya existe un grupo con ese nombre ❌", "error")
            return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

    # GET
    return render_template("crear_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))


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

                if grupo["contrasena"] not in (None, "") and grupo["contrasena"] != contrasena:
                    flash("Contraseña incorrecta ❌", "error")
                    return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))

                cur.execute(
                    "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
                    (grupo["id"], usuario_id)
                )
                conn.commit()

        session["grupo_actual"] = grupo["codigo"]  # opcional
        flash(f"Te has unido al grupo '{grupo['codigo']}' 🎉", "success")
        return redirect(url_for("grupos.gestionar_grupos"))

    # GET
    return render_template("unirse_grupo.html", grupos_usuario=get_grupos_usuario(usuario_id))


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

            # ¿Pertenece a ese grupo?
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

            # ¿Cuántos grupos tiene en total?
            cur.execute("SELECT COUNT(*) FROM Grupo_Usuario WHERE id_usuario = ?", (usuario_id,))
            total = cur.fetchone()[0]
            if total <= 1:
                flash("No puedes salirte de tu único grupo. Únete a otro antes.", "warning")
                return redirect(url_for("grupos.gestionar_grupos"))

            # Borrar relación
            cur.execute(
                "DELETE FROM Grupo_Usuario WHERE id_usuario = ? AND id_grupo = ?",
                (usuario_id, id_grupo)
            )
            conn.commit()

            # Si salía del grupo guardado en sesión, fijar otro
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
