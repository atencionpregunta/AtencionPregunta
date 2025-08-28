import os
from flask import Flask, session, render_template
from flask_dance.contrib.google import make_google_blueprint
from dotenv import load_dotenv
# from apscheduler.schedulers.background import BackgroundScheduler  # opcional
# from apscheduler.triggers.cron import CronTrigger                  # opcional
# from zoneinfo import ZoneInfo                                      # opcional

# ----------------------------
# Cargar variables de entorno
# ----------------------------
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# ----------------------------
# ÚNICA instancia de Flask
# ----------------------------
app = Flask(__name__)
# Clave de sesión (firmado de cookies)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "I2k4e1r22001!")
# Contraseña de administrador (separada de la secret_key)
app.config["ADMIN_PASSWORD"] = os.getenv("ADMIN_PASSWORD", "I2k4e1r22001!")

# ----------------------------
# Google OAuth (Flask-Dance)
# ----------------------------
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
# Asegurar nombre del endpoint "google"
google_bp.name = "google"

# Registra ANTES de rutas que renderizan plantillas
app.register_blueprint(google_bp, url_prefix="/login")

# ----------------------------
# Blueprints propios
# ----------------------------
from auth import auth_bp
from grupos import grupos_bp
from preguntas import preguntas_bp
from resultados import resultados_bp
from admin import admin_bp  # import directo para evitar ciclos

app.register_blueprint(auth_bp)
app.register_blueprint(grupos_bp)
app.register_blueprint(preguntas_bp)   # si quieres prefix, ponlo en ese blueprint
app.register_blueprint(resultados_bp)
app.register_blueprint(admin_bp)       # SIN url_prefix; las rutas ya empiezan por /admin



# ----------------------------
# Ruta principal
# ----------------------------
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
                """
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND DATE(fecha) = ?
                """,
                (usuario_id, fecha_hoy),
            )
            ya_respondido = cursor.fetchone() is not None

    id_grupo = None
    if grupo_actual:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Grupos WHERE codigo = ?", (grupo_actual,))
            grupo = cursor.fetchone()
            if grupo:
                id_grupo = grupo["id"]

    return render_template(
        "index.html",
        grupo_actual=grupo_actual,
        ya_respondido=ya_respondido,
        id_grupo=id_grupo,
    )

# ----------------------------
# Arranque local
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(app.url_map)  # para verificar endpoints (deberías ver google.login y admin.*)
    app.run(host="0.0.0.0", port=port, debug=True)
    
from flask_cors import CORS
# si servirás React en otro dominio (p.ej. https://tu-frontend.com):
CORS(app, resources={r"/api/*": {"origins": ["https://tu-frontend.com"], "supports_credentials": True}})
app.config.update(
    SESSION_COOKIE_SAMESITE="None",   # cookies cross-site
    SESSION_COOKIE_SECURE=True        # requiere HTTPS en prod
)
