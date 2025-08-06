import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_por_defecto")

# Configurar blueprint de Google
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    redirect_url="/google/callback",
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
)
app.register_blueprint(google_bp, url_prefix="/login")

# Funciones auxiliares
def get_pregunta_del_dia():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Preguntas ORDER BY RANDOM() LIMIT 1")
    pregunta = cursor.fetchone()
    cursor.execute("SELECT * FROM Respuestas WHERE id_pregunta = ?", (pregunta["id"],))
    respuestas = cursor.fetchall()
    conn.close()
    return pregunta, respuestas

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/crear_usuario", methods=["GET", "POST"])
def crear_usuario():
    if request.method == "GET":
        return render_template("crear_usuario.html")

    usuario = request.form["usuario"]
    mail = request.form["mail"]
    contrasena = request.form["contrasena"]
    pais = request.form["pais"]
    edad = request.form["edad"]

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO Usuarios (usuario, mail, contrasena, fec_ini, pais, edad)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (usuario, mail, contrasena, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pais, edad))
    conn.commit()
    conn.close()

    return redirect(url_for("login_form"))

@app.route("/login", methods=["GET", "POST"])
def login_form():
    if request.method == "GET":
        return render_template("login.html")

    usuario = request.form["usuario"]
    contrasena = request.form["contrasena"]

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Usuarios WHERE usuario = ?", (usuario,))
    user = cursor.fetchone()
    conn.close()

    if user and user["contrasena"] == contrasena:
        session["usuario_id"] = user["id"]
        session["usuario_nombre"] = user["usuario"]
        return redirect(url_for("index"))
    else:
        return "Usuario o contraseña incorrectos"

@app.route("/google/callback")
def google_callback():
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

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Usuarios WHERE mail = ?", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("""
            INSERT INTO Usuarios (mail, usuario, contrasena, fec_ini, pais, edad)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (email, nombre, None, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Google", None))
        conn.commit()
        cursor.execute("SELECT * FROM Usuarios WHERE mail = ?", (email,))
        user = cursor.fetchone()

    conn.close()

    session["usuario_id"] = user["id"]
    session["usuario_nombre"] = user["usuario"]

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/aceptar_reto", methods=["POST"])
def aceptar_reto():
    if "usuario_id" not in session:
        return redirect(url_for("login_form"))
    pregunta, respuestas = get_pregunta_del_dia()
    return render_template("pregunta.html", pregunta=pregunta, respuestas=respuestas)

@app.route("/responder", methods=["POST"])
def responder():
    if "usuario_id" not in session:
        return redirect(url_for("login_form"))

    id_respuesta = request.form.get("respuesta")

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
    respuesta = cursor.fetchone()

    cursor.execute("SELECT * FROM Preguntas WHERE id = ?", (respuesta["id_pregunta"],))
    pregunta = cursor.fetchone()

    puntuacion = 1 if respuesta["correcta"] else 0

    cursor.execute('''
        INSERT INTO Resultados (fecha, id_usuario, id_grupo, temporada, id_pregunta, id_respuesta, puntuacion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session["usuario_id"],
        1, "2025-T1",
        respuesta["id_pregunta"],
        respuesta["id"],
        puntuacion
    ))
    conn.commit()
    conn.close()

    return f"✅ Respuesta registrada. Puntos: {puntuacion}"

if __name__ == "__main__":
<<<<<<< HEAD
    port = int(os.environ.get("PORT", 5000))  # Render te da el puerto como variable
    app.run(host="0.0.0.0", port=port, debug=True)
=======
    app.run(debug=True)
>>>>>>> b0d0739b4a8738280fab6ff4e903bcaadb565113
