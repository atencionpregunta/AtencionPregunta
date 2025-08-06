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

def get_grupo_actual(usuario_id):
    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT G.codigo FROM Grupos G
                JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
                WHERE GU.id_usuario = ?
            """, (usuario_id,))
            row = cursor.fetchone()
            return row["codigo"] if row else None

@app.route("/")
def index():
    usuario_id = session.get("usuario_id")
    grupo_actual = get_grupo_actual(usuario_id) if usuario_id else None
    print("DEBUG grupo_actual:", grupo_actual)
    return render_template("index.html", grupo_actual=grupo_actual)


@app.route("/salir_grupo", methods=["POST"])
def salir_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        flash("Debes iniciar sesión.", "error")
        return redirect(url_for("index"))

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()

            # Buscar el grupo actual del usuario
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

@app.route("/crear_grupo", methods=["GET", "POST"])
def crear_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("login_form"))

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
            return redirect(url_for("crear_grupo"))

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
        except sqlite3.IntegrityError:
            flash("Ya existe un grupo con ese nombre ❌", "error")

    return render_template("crear_grupo.html")

@app.route("/unirse_grupo", methods=["GET", "POST"])
def unirse_grupo():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect(url_for("login_form"))

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

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM Resultados
            WHERE id_usuario = ? AND DATE(fecha) = ?
        """, (usuario_id, fecha_hoy))
        ya_respondido = cursor.fetchone() is not None

    if ya_respondido:
        flash("Ya has respondido hoy. Solo puedes participar una vez.")
        return redirect(url_for("ver_resultados"))

    # Si no ha respondido, carga la pregunta
    pregunta, respuestas = get_pregunta_del_dia()
    return render_template("pregunta.html", pregunta=pregunta, respuestas=respuestas, ya_respondido=False)


def get_puntuacion_anterior(id_usuario):
    fecha_actual = datetime.today().isoformat()  # 'YYYY-MM-DD'
    
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT puntuacion
            FROM Resultados
            WHERE id_usuario = ?
              AND fecha < ?
            ORDER BY fecha DESC
            LIMIT 1
        """, (id_usuario, fecha_actual))
        resultado = cursor.fetchone()
        return resultado["puntuacion"] if resultado else None



@app.route("/responder", methods=["POST"])
def responder():
    if "usuario_id" not in session:
        return redirect(url_for("login_form"))

    usuario_id = session["usuario_id"]
    fecha_hoy = datetime.now().date().isoformat()

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND DATE(fecha) = ?
            """, (usuario_id, fecha_hoy))

            if cursor.fetchone():
                flash("Ya has respondido hoy. Solo puedes responder una vez.")
                return redirect(url_for("ver_resultados"))

    puntuacion_anterior = get_puntuacion_anterior(usuario_id) or 0
    id_respuesta = request.form.get("respuesta")

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")

            cursor.execute("SELECT * FROM Respuestas WHERE id = ?", (id_respuesta,))
            respuesta = cursor.fetchone()

            if not respuesta:
                return "❌ Error: respuesta no encontrada"

            cursor.execute("SELECT * FROM Preguntas WHERE id = ?", (respuesta["id_pregunta"],))
            pregunta = cursor.fetchone()

            grupo_codigo = session.get("grupo_actual")
            id_grupo = None
            if grupo_codigo:
                cursor.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_codigo,))
                grupo = cursor.fetchone()
                if grupo:
                    id_grupo = grupo["id"]

            if None in (session.get("usuario_id"), id_grupo, respuesta["id"], respuesta["id_pregunta"]):
                return "❌ Error interno: datos incompletos."

            correcta = int(respuesta["correcta"])
            puntuacion = puntuacion_anterior + 1  if correcta else puntuacion_anterior
            temporada = "2025-T1"

            cursor.execute('''
                INSERT INTO Resultados (fecha, id_usuario, id_grupo, temporada, puntuacion, correcta, id_pregunta, id_respuesta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session["usuario_id"],
                id_grupo,
                temporada,
                puntuacion,
                correcta,
                respuesta["id_pregunta"],
                respuesta["id"]
            ))

            conn.commit()

    return render_template("resultado.html", correcta=bool(correcta), puntuacion=puntuacion)



def get_pregunta_del_dia():
    today = datetime.now().date()

    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM Preguntas WHERE fecha_mostrada = ?
            """, (today,))
            pregunta = cursor.fetchone()

            if not pregunta:
                cursor.execute("""
                    SELECT * FROM Preguntas
                    WHERE fecha_mostrada IS NULL
                    ORDER BY RANDOM()
                    LIMIT 1
                """)
                pregunta = cursor.fetchone()

                if pregunta:
                    cursor.execute("""
                        UPDATE Preguntas SET fecha_mostrada = ?
                        WHERE id = ?
                    """, (today, pregunta["id"]))
                    conn.commit()

            if not pregunta:
                return None, []

            cursor.execute("SELECT * FROM Respuestas WHERE id_pregunta = ?", (pregunta["id"],))
            respuestas = cursor.fetchall()

            return pregunta, respuestas

@app.route("/resultados")
def ver_resultados():
    fecha_hoy = datetime.today().strftime("%Y-%m-%d")

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT U.usuario, SUM(R.puntuacion) AS puntuacion
            FROM Resultados R
            JOIN Usuarios U ON R.id_usuario = U.id
            WHERE DATE(R.fecha) = ?
            GROUP BY R.id_usuario
            ORDER BY puntuacion DESC
        """, (fecha_hoy,))
        participantes = cursor.fetchall()

    return render_template("resultado.html", participantes=participantes)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)