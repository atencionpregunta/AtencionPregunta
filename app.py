import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_dance.contrib.google import make_google_blueprint, google
from datetime import datetime
from dotenv import load_dotenv
import threading

# Cargar variables de entorno
load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_por_defecto")

db_lock = threading.RLock()

# Blueprint de Google OAuth
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

# Función para conexión SQLite
def get_conn():
    conn = sqlite3.connect("database.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Función auxiliar para obtener pregunta del día
def get_pregunta_del_dia():
    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Preguntas ORDER BY RANDOM() LIMIT 1")
            pregunta = cursor.fetchone()
            cursor.execute("SELECT * FROM Respuestas WHERE id_pregunta = ?", (pregunta["id"],))
            respuestas = cursor.fetchall()
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

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO Usuarios (usuario, mail, contrasena, fec_ini, pais, edad)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (usuario, mail, contrasena, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pais, edad))
            conn.commit()

    return redirect(url_for("login_form"))

@app.route("/login", methods=["GET", "POST"])
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

    with db_lock:
        with get_conn() as conn:
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

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
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

    return f"✅ Respuesta registrada. Puntos: {puntuacion}"

def registrar_usuario_en_grupo(conn, grupo_id, usuario_id):
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)", (grupo_id, usuario_id))

@app.route("/crear_grupo", methods=["GET", "POST"])
def crear_grupo():
    if request.method == "POST":
        nombre = request.form["nombre_grupo"].strip()
        contrasena = request.form["contrasena_grupo"].strip()
        usuario_id = session.get("usuario_id")

        if not nombre or not usuario_id:
            flash("Faltan datos para crear el grupo.", "error")
            return redirect(url_for("crear_grupo"))

        try:
            with db_lock:
                with get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO Grupos (fec_ini, codigo, tipo, contrasena) VALUES (?, ?, ?, ?)", (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nombre, "general", contrasena or None))
                    grupo_id = cursor.lastrowid
                    registrar_usuario_en_grupo(conn, grupo_id, usuario_id)
                    session["grupo_actual"] = nombre
                    flash(f"Grupo '{nombre}' creado correctamente ✅", "success")
                    return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("Ya existe un grupo con ese nombre ❌", "error")

    return render_template("crear_grupo.html")

@app.route("/unirse_grupo", methods=["GET", "POST"])
def unirse_grupo():
    grupos_usuario = []
    usuario_id = session.get("usuario_id")

    if usuario_id:
        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT G.* FROM Grupos G
                    INNER JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
                    WHERE GU.id_usuario = ?
                ''', (usuario_id,))
                grupos_usuario = cursor.fetchall()

    if request.method == "POST":
        codigo = request.form["codigo_grupo"].strip()
        contrasena = request.form["contrasena_grupo"].strip()

        if not usuario_id:
            flash("Debes iniciar sesión para unirte a un grupo.", "error")
            return redirect(url_for("login_form"))

        with db_lock:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM Grupos WHERE codigo = ?", (codigo,))
                grupo = cursor.fetchone()

                if grupo:
                    if grupo["contrasena"] is None or grupo["contrasena"] == contrasena:
                        registrar_usuario_en_grupo(conn, grupo["id"], usuario_id)
                        session["grupo_actual"] = grupo["codigo"]
                        flash(f"Te has unido al grupo '{grupo['codigo']}' 🎉", "success")
                        return redirect(url_for("index"))
                    else:
                        flash("Contraseña incorrecta ❌", "error")
                else:
                    flash("Grupo no encontrado ❌", "error")

    return render_template("unirse_grupo.html", grupos_usuario=grupos_usuario)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
