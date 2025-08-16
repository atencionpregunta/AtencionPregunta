from flask import render_template, request, redirect, session, url_for, flash, jsonify
from datetime import datetime
from db import get_conn, db_lock
from . import auth_bp
import sqlite3
import re

# Seguridad
from werkzeug.security import generate_password_hash, check_password_hash

# --------- Helpers de existencia ----------
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

# --------- Endpoints AJAX para “disponible” ----------
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
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", mail):
        return jsonify({"available": False, "reason": "invalid"})
    return jsonify({"available": not mail_existe(mail)})

# --------- Registro ----------
@auth_bp.route("/crear_usuario", methods=["GET", "POST"])
def crear_usuario():
    if request.method == "GET":
        return render_template("crear_usuario.html")

    usuario    = (request.form.get("usuario") or "").strip()
    mail       = (request.form.get("mail") or "").strip()
    contrasena = (request.form.get("contrasena") or "")
    pais       = (request.form.get("pais") or "").strip()
    edad_raw   = (request.form.get("edad") or "").strip()
    edad       = int(edad_raw) if edad_raw.isdigit() else None

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
        return render_template("crear_usuario.html",
                               usuario=usuario, mail=mail, pais=pais, edad=edad_raw)

    try:
        with db_lock:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO Usuarios (usuario, mail, contrasena, fec_ini, pais, edad)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    usuario,
                    mail,
                    generate_password_hash(contrasena),  # ← hash seguro
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    (pais or None),
                    edad
                ))
                conn.commit()
    except sqlite3.IntegrityError:
        # Por si ya hay UNIQUE en BD y entran dos a la vez
        flash("El usuario o email ya existe.", "error")
        return render_template("crear_usuario.html",
                               usuario=usuario, mail=mail, pais=pais, edad=edad_raw)

    flash("Cuenta creada. ¡Inicia sesión!", "success")
    return redirect(url_for("auth.login_form"))

# --------- Login ----------
@auth_bp.route("/login", methods=["GET", "POST"])
def login_form():
    if request.method == "GET":
        return render_template("login.html")

    usuario = (request.form.get("usuario") or "").strip()
    contrasena = request.form.get("contrasena") or ""

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            # Permite login por usuario (no por email); si quieres por email cambia la columna
            cursor.execute("SELECT * FROM Usuarios WHERE usuario = ? COLLATE NOCASE", (usuario,))
            user = cursor.fetchone()

    if user and user["contrasena"] and check_password_hash(user["contrasena"], contrasena):
        session["usuario_id"] = user["id"]
        session["usuario_nombre"] = user["usuario"]
        return redirect(url_for("index"))

    flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html", usuario=usuario)

# --------- Google OAuth callback ----------
@auth_bp.route("/google/callback")
def google_callback():
    from flask_dance.contrib.google import google
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
    except Exception as e:
        flash(f"Error al obtener datos de Google: {e}", "error")
        return redirect(url_for("auth.login_form"))

    if not resp.ok:
        flash("Error al obtener datos de usuario de Google.", "error")
        return redirect(url_for("auth.login_form"))

    info = resp.json()
    email = info.get("email")
    nombre = info.get("name") or email
    if not email:
        flash("No se pudo obtener el email desde Google.", "error")
        return redirect(url_for("auth.login_form"))

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
                    None,  # sin contraseña (login social)
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
