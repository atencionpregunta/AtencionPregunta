from flask import render_template, request, redirect, session, url_for
from datetime import datetime
from db import get_conn, db_lock
from . import auth_bp  # <-- aquí está el cambio clave
from flask import render_template, request, redirect, session, url_for, flash, jsonify
from datetime import datetime
from db import get_conn, db_lock
from . import auth_bp
import sqlite3
import re

def usuario_existe(usuario: str) -> bool:
    u = (usuario or "").strip()
    if not u:
        return False
    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM Usuarios WHERE usuario = ? COLLATE NOCASE LIMIT 1", (u,))
            return cur.fetchone() is not None

def mail_existe(mail: str) -> bool:
    m = (mail or "").strip()
    if not m:
        return False
    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM Usuarios WHERE mail = ? COLLATE NOCASE LIMIT 1", (m,))
            return cur.fetchone() is not None

@auth_bp.route("/check_usuario")
def check_usuario():
    usuario = (request.args.get("usuario") or "").strip()
    if not usuario:
        return jsonify({"available": False})
    return jsonify({"available": not usuario_existe(usuario)})

@auth_bp.route("/check_mail")
def check_mail():
    mail = (request.args.get("mail") or "").strip()
    if not mail:
        return jsonify({"available": False})
    # Comprobación rápida de formato para evitar consultas innecesarias
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", mail):
        return jsonify({"available": False, "reason": "invalid"})
    return jsonify({"available": not mail_existe(mail)})

@auth_bp.route("/crear_usuario", methods=["GET", "POST"])
def crear_usuario():
    if request.method == "GET":
        return render_template("crear_usuario.html")

    usuario   = (request.form.get("usuario") or "").strip()
    mail      = (request.form.get("mail") or "").strip()
    contrasena= (request.form.get("contrasena") or "")
    pais      = (request.form.get("pais") or "").strip()
    edad_raw  = (request.form.get("edad") or "").strip()
    edad      = int(edad_raw) if edad_raw.isdigit() else None

    # Validaciones servidor
    errores = []
    if not usuario:
        errores.append("El nombre de usuario es obligatorio.")
    if not mail:
        errores.append("El email es obligatorio.")
    elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", mail):
        errores.append("El email no tiene un formato válido.")
    if len(contrasena) < 4:
        errores.append("La contraseña debe tener al menos 4 caracteres.")
    if usuario_existe(usuario):
        errores.append("Ese nombre de usuario ya está en uso.")
    if mail_existe(mail):
        errores.append("Ese email ya está en uso.")

    if errores:
        for e in errores:
            flash(e, "error")
        # Volvemos al formulario preservando los campos rellenados (excepto contraseña)
        return render_template("crear_usuario.html")

    try:
        with db_lock:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO Usuarios (usuario, mail, contrasena, fec_ini, pais, edad)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    usuario, mail, contrasena,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    pais or None, edad
                ))
                conn.commit()
    except sqlite3.IntegrityError:
        # Por si hay UNIQUE en BD o carrera entre dos altas
        flash("El usuario o email ya existe.", "error")
        return render_template("crear_usuario.html")

    return redirect(url_for("auth.login_form"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login_form():
    if request.method == "GET":
        return render_template("login.html")

    usuario = request.form["usuario"]
    contrasena = request.form["contrasena"]

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Usuarios WHERE usuario = ?", (usuario,))
            user = cursor.fetchone()

    if user and user["contrasena"] == contrasena:
        session["usuario_id"] = user["id"]
        session["usuario_nombre"] = user["usuario"]
        return redirect(url_for("index"))
    else:
        return "Usuario o contraseña incorrectos"

@auth_bp.route("/google/callback")
def google_callback():
    from flask_dance.contrib.google import google
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
    except Exception as e:
        return f"Error al obtener datos de usuario: {e}"

    if not resp.ok:
        return "❌ Error al obtener datos del usuario"

    info = resp.json()
    email = info.get("email")
    nombre = info.get("name", email)

    if not email:
        return "❌ Error: no se obtuvo el email"

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Usuarios WHERE mail = ?", (email,))
            user = cursor.fetchone()

            if not user:
                cursor.execute("""
                    INSERT INTO Usuarios (mail, usuario, contrasena, fec_ini, pais, edad)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    email,
                    nombre,
                    None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Google",
                    None
                ))
                conn.commit()

                cursor.execute("SELECT * FROM Usuarios WHERE mail = ?", (email,))
                user = cursor.fetchone()

    session["usuario_id"] = user["id"]
    session["usuario_nombre"] = user["usuario"]
    return redirect(url_for("index"))

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
