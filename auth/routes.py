from flask import render_template, request, redirect, session, url_for
from datetime import datetime
from db import get_conn, db_lock
from . import auth_bp  # <-- aquí está el cambio clave

@auth_bp.route("/crear_usuario", methods=["GET", "POST"])
def crear_usuario():
    if request.method == "GET":
        return render_template("crear_usuario.html")

    usuario = request.form["usuario"]
    mail = request.form["mail"]
    contrasena = request.form["contrasena"]
    pais = request.form["pais"]
    edad = request.form["edad"] or None  # Evitar string vacío

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO Usuarios (usuario, mail, contrasena, fec_ini, pais, edad)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (usuario, mail, contrasena, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pais, edad))
            conn.commit()

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
