import os
from flask import Flask, session, render_template
from flask_dance.contrib.google import make_google_blueprint
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo  # Py>=3.9
from utils import _seleccionar_pregunta_para_hoy, email_puede_buscar


# Cargar variables de entorno
load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_por_defecto")

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

# Importar y registrar Blueprints de tus módulos
from auth import auth_bp
from grupos import grupos_bp
from preguntas import preguntas_bp
from resultados import resultados_bp
from busquedas.routes import busquedas_bp

app.register_blueprint(auth_bp)
app.register_blueprint(grupos_bp)
app.register_blueprint(preguntas_bp)  
app.register_blueprint(resultados_bp)
app.register_blueprint(busquedas_bp)

# Ruta principal
@app.route("/")
def index():
    from utils import get_grupo_actual
    from db import get_conn
    from datetime import datetime

    usuario_id = session.get("usuario_id")
    grupo_actual = get_grupo_actual(usuario_id) if usuario_id else None
    ya_respondido = False
    usuario_email = session.get("usuario_email")
    puede_buscar_por_email = email_puede_buscar(usuario_email)

    if usuario_id:
        fecha_hoy = datetime.now().date().isoformat()
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM Resultados
                WHERE id_usuario = ? AND DATE(fecha) = ?
            """, (usuario_id, fecha_hoy))
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
        puede_buscar_por_email = puede_buscar_por_email
    )


# Ejecutar la app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(app.url_map)
    app.run(host="0.0.0.0", port=port, debug=True)
