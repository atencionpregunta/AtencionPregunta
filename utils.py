from datetime import datetime
from db import get_conn
from functools import wraps
from flask import session, redirect, url_for, flash

def get_puntuacion_anterior(id_usuario):
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT puntuacion FROM Resultados
            WHERE id_usuario = ? AND fecha < ?
            ORDER BY fecha DESC
            LIMIT 1
        """, (id_usuario, fecha_actual))
        resultado = cursor.fetchone()
        return resultado["puntuacion"] if resultado else None
     
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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "error")
            return redirect(url_for("auth.login_form"))
        return f(*args, **kwargs)
    return decorated_function

from db import get_conn, db_lock
from datetime import datetime

def get_pregunta_del_dia():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Preguntas ORDER BY fecha_mostrada DESC LIMIT 1")
        pregunta = cursor.fetchone()

        if not pregunta:
            return None

        cursor.execute("SELECT * FROM Respuestas WHERE id_pregunta = ?", (pregunta["id"],))
        respuestas = cursor.fetchall()

        return pregunta, respuestas  # ✅ importante: devuelve tupla
