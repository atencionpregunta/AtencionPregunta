import os
from flask import Flask, session, render_template
from flask_dance.contrib.google import make_google_blueprint
from dotenv import load_dotenv
from utils import ensure_schema_usuarios   # 👈 import aquí
from datetime import timedelta


# --- 1) Cargar .env ---
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # solo local

# --- 2) Crear app ---
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "I2k4e1r22001!")
app.config["ADMIN_PASSWORD"] = os.getenv("ADMIN_PASSWORD", "I2k4e1r22001!")

app.permanent_session_lifetime = timedelta(days=30)  # cookie de Flask válida 30 días
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,  # pon True si sirves por HTTPS
)


# (Opcional) CORS y cookies cross-site (poner antes de blueprints)
from flask_cors import CORS
CORS(app, resources={r"/api/*": {"origins": ["https://tu-frontend.com"], "supports_credentials": True}})
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True
)

# --- 3) Inicializar BD (elige UNA vía) ---
# Opción A: hacerlo aquí (si NO usas start.sh para init):
# from db_bootstrap import bootstrap_db
# bootstrap_db()

# Opción B: dejar que start.sh ejecute `python init_db.py` (recomendado en Render)
# y no llamar a nada aquí.

# --- 4) Google OAuth ---
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    redirect_url="/google/callback",
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
)
google_bp.name = "google"
app.register_blueprint(google_bp, url_prefix="/login")


ensure_schema_usuarios()

# --- 5) Blueprints propios ---
from auth import auth_bp
from grupos import grupos_bp
from preguntas import preguntas_bp
from resultados import resultados_bp
from admin import admin_bp
from chat import chat_bp

app.register_blueprint(auth_bp)
app.register_blueprint(grupos_bp)
app.register_blueprint(preguntas_bp)
app.register_blueprint(resultados_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(chat_bp)

# --- 6) Ruta principal ---
@app.route("/")
def index():
    from utils import get_grupo_actual
    from db import get_conn
    from datetime import datetime

    usuario_id = session.get("usuario_id")
    grupo_actual = get_grupo_actual(usuario_id) if usuario_id else None
    ya_respondido = False

    if usuario_id:
        fecha_hoy = datetime.now().date().isoformat()
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM Resultados WHERE id_usuario = ? AND DATE(fecha) = ?",
                (usuario_id, fecha_hoy),
            )
            ya_respondido = cursor.fetchone() is not None

    id_grupo = None
    if grupo_actual:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_actual,))
            row = cursor.fetchone()
            if row:
                id_grupo = row["id"]

    return render_template("index.html", grupo_actual=grupo_actual, ya_respondido=ya_respondido, id_grupo=id_grupo)

# --- 7) Arranque local ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # print(app.url_map)  # útil para depurar, comenta en prod
    app.run(host="0.0.0.0", port=port, debug=True)
