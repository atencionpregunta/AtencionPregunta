from flask import request, redirect, render_template, session, url_for, flash
from datetime import datetime
from db import get_conn, db_lock
from . import grupos_bp  # ← esta es la línea importante

@grupos_bp.route("/crear_grupo", methods=["GET", "POST"])
def crear_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Grupo_Usuario WHERE id_usuario = ?", (usuario_id,))
            en_grupo = cursor.fetchone()[0]
            if en_grupo >= 1:
                flash("Ya perteneces a un grupo. Debes salir antes de crear otro.", "error")
                return redirect(url_for("index"))

    if request.method == "POST":
        nombre = request.form["nombre_grupo"].strip()
        contrasena = request.form["contrasena_grupo"].strip()

        if not nombre:
            flash("Falta el nombre del grupo.", "error")
            return redirect(url_for("grupos.crear_grupo"))

        try:
            with db_lock:
                with get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Grupos (fec_ini, codigo, tipo, contrasena) VALUES (?, ?, ?, ?)", (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nombre, "general", contrasena or None))
                    grupo_id = cursor.lastrowid
                    cursor.execute("INSERT INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)", (grupo_id, usuario_id))
                    conn.commit()
                    session["grupo_actual"] = nombre
                    flash(f"Grupo '{nombre}' creado correctamente ✅", "success")
                    return redirect(url_for("index"))
        except:
            flash("Ya existe un grupo con ese nombre ❌", "error")

    return render_template("crear_grupo.html")

@grupos_bp.route("/unirse_grupo", methods=["GET", "POST"])
def unirse_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("auth.login_form"))

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Grupo_Usuario WHERE id_usuario = ?", (usuario_id,))
            en_grupo = cursor.fetchone()[0]
            if en_grupo >= 1:
                flash("Ya perteneces a un grupo. Debes salir antes de unirte a otro.", "error")
                return redirect(url_for("index"))

    if request.method == "POST":
        codigo = request.form["codigo_grupo"].strip()
        contrasena = request.form["contrasena_grupo"].strip()

        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM Grupos WHERE codigo = ?", (codigo,))
                grupo = cursor.fetchone()

                if grupo:
                    if grupo["contrasena"] is None or grupo["contrasena"] == contrasena:
                        cursor.execute("INSERT INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)", (grupo["id"], usuario_id))
                        conn.commit()
                        session["grupo_actual"] = grupo["codigo"]
                        flash(f"Te has unido al grupo '{grupo['codigo']}' 🎉", "success")
                        return redirect(url_for("index"))
                    else:
                        flash("Contraseña incorrecta ❌", "error")
                else:
                    flash("Grupo no encontrado ❌", "error")

    return render_template("unirse_grupo.html")

@grupos_bp.route("/salir_grupo", methods=["POST"])
def salir_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("index"))

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT G.id, G.codigo FROM Grupos G
                JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
                WHERE GU.id_usuario = ?
            """, (usuario_id,))
            grupo = cursor.fetchone()

            if grupo:
                cursor.execute("""
                    DELETE FROM Grupo_Usuario
                    WHERE id_grupo = ? AND id_usuario = ?
                """, (grupo["id"], usuario_id))
                conn.commit()
                flash(f"Has salido del grupo '{grupo['codigo']}' ✅", "success")
            else:
                flash("No perteneces a ningún grupo.", "info")

    return redirect(url_for("index"))
