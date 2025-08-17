from datetime import datetime
from db import get_conn
from functools import wraps
from flask import session, redirect, url_for, flash

def get_puntuacion_anterior(id_usuario, id_grupo):
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT max(puntuacion) FROM Resultados
            WHERE id_usuario = ? AND id_grupo = ?
            ORDER BY fecha DESC
            LIMIT 1
        """, (id_usuario, id_grupo))
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
        
def get_id_grupo_actual(usuario_id):
    with db_lock:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT G.id FROM Grupos G
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

from datetime import datetime
from db import get_conn, db_lock

# utils.py
from datetime import datetime, time
from db import get_conn, db_lock

HUSO = "Europe/Madrid"  # solo a título informativo si usas zoneinfo en app.py
HORA_SELECCION = time(9, 0, 0)  # 09:00

def _seleccionar_pregunta_para_hoy():
    """Elige una pregunta NO mostrada y la marca con fecha_mostrada=ahora.
       Si ya hay una para hoy, no hace nada. Idempotente."""
    hoy = datetime.now().date().isoformat()
    with db_lock:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            # ¿Ya hay pregunta fijada hoy?
            c.execute("""
                SELECT id FROM Preguntas
                WHERE substr(COALESCE(fecha_mostrada, ''), 1, 10) = ?
                LIMIT 1
            """, (hoy,))
            if c.fetchone():
                conn.commit()
                return

            # Elegir una NO mostrada (NULL primero), y si todas mostradas, la menos reciente
            c.execute("""
                SELECT *
                FROM Preguntas
                ORDER BY
                    CASE WHEN fecha_mostrada IS NULL THEN 0 ELSE 1 END ASC,
                    fecha_mostrada ASC,
                    RANDOM()
                LIMIT 1
            """)
            preg = c.fetchone()
            if not preg:
                conn.commit()
                return

            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?", (ahora, preg["id"]))
            conn.commit()

# utils.py
from datetime import datetime, time
from db import get_conn, db_lock

HORA_SELECCION = time(9, 0, 0)  # ajusta si quieres otra hora

def get_pregunta_del_dia():
    """
    - Si ya hay pregunta con fecha_mostrada = hoy, devuelve esa.
    - Si no hay y ya pasó HORA_SELECCION, elige una (NULL primero, luego la más antigua) y la marca.
    - Carga SIEMPRE las respuestas antes de salir del 'with'.
    """
    ahora = datetime.now()
    hoy = ahora.date().isoformat()

    with db_lock:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")
            # 1) ¿Ya hay fijada hoy?
            c.execute("""
                SELECT * FROM Preguntas
                WHERE substr(COALESCE(fecha_mostrada,''),1,10) = ?
                LIMIT 1
            """, (hoy,))
            pregunta = c.fetchone()

            # 2) Si no hay y ya pasó la hora “oficial”, elegimos y marcamos ahora
            if not pregunta and ahora.time() >= HORA_SELECCION:
                # Elegir una no mostrada antes (NULL) y si no, la menos reciente.
                c.execute("""
                    SELECT *
                    FROM Preguntas
                    ORDER BY 
                        CASE WHEN fecha_mostrada IS NULL THEN 0 ELSE 1 END ASC,
                        fecha_mostrada ASC,
                        RANDOM()
                    LIMIT 1
                """)
                pregunta = c.fetchone()
                if pregunta:
                    c.execute(
                        "UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?",
                        (ahora.strftime("%Y-%m-%d %H:%M:%S"), pregunta["id"])
                    )

            # 3) Si seguimos sin pregunta, no mostramos nada
            if not pregunta:
                conn.commit()
                return None, []

            # 4) Cargar respuestas ANTES de salir del with (mientras la conexión sigue abierta)
            c.execute("SELECT * FROM Respuestas WHERE id_pregunta = ? ORDER BY id", (pregunta["id"],))
            respuestas = c.fetchall()

            conn.commit()
            return pregunta, respuestas
