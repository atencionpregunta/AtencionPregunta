# utils.py
from __future__ import annotations
from datetime import datetime, timedelta, time
from functools import wraps
from zoneinfo import ZoneInfo
from flask import session, redirect, url_for, flash

from db import get_conn, db_lock

# =========================
# Zona horaria y “día efectivo”
# =========================
TZ = ZoneInfo("Europe/Madrid")
HORA_SELECCION = time(9, 0, 0)  # hora local de publicación (corte de día)

def _ahora_local() -> datetime:
    return datetime.now(TZ)

def _ahora_local_str() -> str:
    return _ahora_local().strftime("%Y-%m-%d %H:%M:%S")

def _hoy_local_str() -> str:
    return _ahora_local().date().isoformat()

def _fecha_efectiva_str() -> str:
    """
    Día 'efectivo' que cambia a las HORA_SELECCION.
    Entre 00:00 y 08:59 devolverá el día anterior; desde 09:00, el día de hoy.
    """
    delta = timedelta(
        hours=HORA_SELECCION.hour,
        minutes=HORA_SELECCION.minute,
        seconds=HORA_SELECCION.second
    )
    return (_ahora_local() - delta).date().isoformat()

# =========================
# Decoradores
# =========================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "error")
            return redirect(url_for("auth.login_form"))
        return f(*args, **kwargs)
    return decorated_function

# =========================
# Helpers de BD (grupos/usuarios)
# =========================
def get_grupo_actual(usuario_id: int) -> str | None:
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT G.codigo
            FROM Grupos G
            JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
            WHERE GU.id_usuario = ?
            ORDER BY G.codigo
            LIMIT 1
        """, (usuario_id,))
        row = cur.fetchone()
        return row["codigo"] if row else None

def get_ids_grupos_usuario(usuario_id: int) -> list[int]:
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT G.id
            FROM Grupos G
            JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
            WHERE GU.id_usuario = ?
            ORDER BY G.codigo
        """, (usuario_id,))
        rows = cur.fetchall()
        return [r["id"] for r in rows]

def get_grupos_usuario(usuario_id: int) -> list[dict]:
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT G.id, G.codigo
            FROM Grupos G
            JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
            WHERE GU.id_usuario = ?
            ORDER BY G.codigo
        """, (usuario_id,))
        rows = cur.fetchall()
    return [dict(id=r["id"], codigo=r["codigo"]) for r in rows]

# =========================
# Puntuaciones
# =========================
def get_puntuacion_anterior(id_usuario: int, id_grupo: int) -> int | None:
    """
    Devuelve la ÚLTIMA puntuación registrada (no el máximo histórico).
    Si quieres el máximo, crea otra función con MAX(puntuacion).
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT puntuacion
            FROM Resultados
            WHERE id_usuario = ? AND id_grupo = ?
            ORDER BY datetime(fecha) DESC
            LIMIT 1
        """, (id_usuario, id_grupo))
        row = cur.fetchone()
        return int(row["puntuacion"]) if row and row["puntuacion"] is not None else None

# =========================
# Pregunta del día
# =========================
# utils.py
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3
from db import get_conn

TZ = ZoneInfo("Europe/Madrid")

# utils.py
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import sqlite3
from db import get_conn, db_lock

TZ = ZoneInfo("Europe/Madrid")
HORA_SELECCION = time(9, 0, 0)  # como ya usabas

def _ahora_local():
    return datetime.now(TZ)

def _ahora_local_str():
    return _ahora_local().strftime("%Y-%m-%d %H:%M:%S")

def _fecha_efectiva_str():
    """
    Día efectivo: antes de las 09:00 cuenta como 'ayer'.
    """
    ahora = _ahora_local()
    corte = ahora.replace(hour=HORA_SELECCION.hour, minute=HORA_SELECCION.minute,
                          second=0, microsecond=0)
    if ahora < corte:
        return (corte.date() - timedelta(days=1)).isoformat()
    return corte.date().isoformat()

def get_pregunta_del_dia():
    """
    Igual que la tuya 'de antes', pero filtrando NO-Relampago.
    Marca Preguntas.fecha_mostrada cuando elija hoy una nueva.
    Devuelve (pregunta_row_as_dict, respuestas_list_as_dict)
    """
    ahora = _ahora_local()
    dia_efectivo = _fecha_efectiva_str()

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")

        # 1) ¿Hay pregunta publicada hoy (NO-Relampago)?
        c.execute("""
            SELECT *
            FROM Preguntas
            WHERE COALESCE(tipo,'') <> 'Relampago'
              AND DATE(fecha_mostrada, 'localtime') = ?
            ORDER BY datetime(fecha_mostrada) DESC
            LIMIT 1
        """, (dia_efectivo,))
        pregunta = c.fetchone()

        # 2) Si no hay y ya pasó la hora de corte, elegimos una y la marcamos ahora
        if not pregunta and ahora.time() >= HORA_SELECCION:
            c.execute("""
                SELECT *
                FROM Preguntas
                WHERE COALESCE(tipo,'') <> 'Relampago'
                ORDER BY
                  (fecha_mostrada IS NOT NULL),       -- NULL primero
                  datetime(fecha_mostrada) ASC,
                  RANDOM()
                LIMIT 1
            """)
            pregunta = c.fetchone()
            if pregunta:
                c.execute(
                    "UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?",
                    (_ahora_local_str(), pregunta["id"])
                )

        # 3) Fallback: última NO-Relampago ya publicada <= ahora
        if not pregunta:
            c.execute("""
                SELECT *
                FROM Preguntas
                WHERE COALESCE(tipo,'') <> 'Relampago'
                  AND fecha_mostrada IS NOT NULL
                  AND datetime(fecha_mostrada) <= ?
                ORDER BY datetime(fecha_mostrada) DESC
                LIMIT 1
            """, (_ahora_local_str(),))
            pregunta = c.fetchone()

        if not pregunta:
            conn.commit()
            return None, []

        # Respuestas
        c.execute("""
            SELECT *
            FROM Respuestas
            WHERE id_pregunta = ?
            ORDER BY id
        """, (pregunta["id"],))
        respuestas = c.fetchall()

        conn.commit()
        return dict(pregunta), [dict(r) for r in respuestas]

def ensure_pack_relampago_hoy(limit: int = 3):
    """
    Asegura que HOY (día efectivo) haya hasta 'limit' preguntas de tipo 'Relampago'
    con fecha_mostrada = hoy (global para todos). Si faltan y ya pasó la hora de corte,
    marca ahora las necesarias. Devuelve la lista ordenada por fecha_mostrada ASC.
    """
    ahora = _ahora_local()
    dia_efectivo = _fecha_efectiva_str()

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")

        # Ya publicadas hoy (Relámpago)
        c.execute("""
            SELECT *
            FROM Preguntas
            WHERE tipo = 'Relampago'
              AND DATE(fecha_mostrada, 'localtime') = ?
            ORDER BY datetime(fecha_mostrada) ASC, id ASC
        """, (dia_efectivo,))
        pack = c.fetchall()

        # Si faltan y ya pasó la hora, publica más hoy
        if len(pack) < limit and ahora.time() >= HORA_SELECCION:
            faltan = limit - len(pack)
            c.execute("""
                SELECT *
                FROM Preguntas
                WHERE tipo = 'Relampago'
                  AND (fecha_mostrada IS NULL OR DATE(fecha_mostrada, 'localtime') <> ?)
                ORDER BY
                  (fecha_mostrada IS NOT NULL),   -- NULL primero
                  datetime(fecha_mostrada) ASC,
                  RANDOM()
                LIMIT ?
            """, (dia_efectivo, faltan))
            nuevos = c.fetchall()

            # Marcar ahora (les podemos dar segundos crecientes para forzar orden estable)
            base = _ahora_local()
            for i, row in enumerate(nuevos):
                ts = (base + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
                c.execute("UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?", (ts, row["id"]))

            # Recargar pack definitivo
            c.execute("""
                SELECT *
                FROM Preguntas
                WHERE tipo = 'Relampago'
                  AND DATE(fecha_mostrada, 'localtime') = ?
                ORDER BY datetime(fecha_mostrada) ASC, id ASC
            """, (dia_efectivo,))
            pack = c.fetchall()

        conn.commit()
        return [dict(r) for r in pack]

# =========================
# Migraciones de esquema
# =========================
def ensure_schema_usuarios():
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(Usuarios)")
        cols = {row[1].lower() for row in cur.fetchall()}

        conn.commit()


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from db import get_conn, db_lock

TZ = ZoneInfo("Europe/Madrid")

# utils_temporadas.py
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from db import get_conn, db_lock

TZ = ZoneInfo("Europe/Madrid")
TODAY = lambda: datetime.now(TZ).date()

def ensure_active_temporada(id_grupo: int):
    """
    Devuelve el id de la temporada ACTIVA del grupo.
    - Si existe y no está caducada, la devuelve.
    - Si existe pero está caducada, la cierra (activa=0) y crea otra nueva desde hoy si el grupo tiene duracion_temp.
    - Si no existe, crea una (si el grupo tiene duracion_temp) o una indefinida.
    """
    with db_lock, get_conn() as conn:
        c = conn.cursor()

        # lee config del grupo
        rowg = c.execute(
            "SELECT fec_ini, duracion_temp FROM Grupos WHERE id=?",
            (id_grupo,)
        ).fetchone()
        if not rowg:
            return None

        dur = rowg["duracion_temp"]
        hoy = TODAY()

        # hay activa?
        temp = c.execute(
            "SELECT * FROM Temporadas WHERE id_grupo=? AND activa=1 LIMIT 1",
            (id_grupo,)
        ).fetchone()

        def create_new():
            # nombre opcional tipo "YYYY-Tn"
            nombre = f"{hoy.year}-T{((hoy.month-1)//3)+1}"
            c.execute("""
              INSERT INTO Temporadas (id_grupo, nombre, fecha_inicio, fecha_fin, duracion_dias, activa)
              VALUES (?, ?, ?, ?, ?, 1)
            """, (
                id_grupo,
                nombre,
                hoy.isoformat(),
                (hoy + timedelta(days=int(dur))).isoformat() if dur else None,
                int(dur) if dur else None
            ))
            return c.lastrowid

        if not temp:
            temporada_id = create_new()
            conn.commit()
            return temporada_id

        # si tiene fecha_fin y ya pasó → cerrar y crear nueva (si el grupo está configurado con duración)
        fecha_fin = temp["fecha_fin"]
        if fecha_fin and date.fromisoformat(fecha_fin) <= hoy:
            c.execute("UPDATE Temporadas SET activa=0 WHERE id=?", (temp["id"],))
            temporada_id = create_new()
            conn.commit()
            return temporada_id

        # sigue activa
        return temp["id"]

def dias_temporada_restantes(id_grupo: int):
    """
    Días restantes de la temporada activa del grupo. None si sin límite.
    0 si termina hoy o está vencida.
    """
    with db_lock, get_conn() as conn:
        c = conn.cursor()
        t = c.execute(
            "SELECT fecha_fin FROM Temporadas WHERE id_grupo=? AND activa=1 LIMIT 1",
            (id_grupo,)
        ).fetchone()

    if not t or not t["fecha_fin"]:
        return None
    hoy = TODAY()
    fin = datetime.strptime(t["fecha_fin"], "%Y-%m-%d").date()
    return max(0, (fin - hoy).days)


from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from db import get_conn, db_lock

TZ = ZoneInfo("Europe/Madrid")

def _hoy():
    return datetime.now(TZ).date()

def ensure_active_temporada(id_grupo: int):
    """
    Devuelve el ID de la temporada activa del grupo.
    - Si no hay activa → crea temporada con nombre numérico (1,2,3...).
    - Si hay activa y está caducada → la cierra y crea otra con el siguiente número.
    - Si hay activa y no está caducada → devuelve su id tal cual.
    (El 'nombre' de Temporadas es SIEMPRE un número en texto, p.ej. '3').
    """
    with db_lock, get_conn() as conn:
        c = conn.cursor()

        g = c.execute(
            "SELECT duracion_temp FROM Grupos WHERE id=?",
            (id_grupo,)
        ).fetchone()
        if not g:
            return None

        dur = g["duracion_temp"]  # puede ser None (indefinida)
        hoy = _hoy()

        # Activa actual
        temp = c.execute(
            "SELECT * FROM Temporadas WHERE id_grupo=? AND activa=1 LIMIT 1",
            (id_grupo,)
        ).fetchone()

        def _next_seq() -> int:
            # Busca el máximo nombre que sea puramente numérico en este grupo
            row = c.execute("""
                SELECT COALESCE(MAX(CAST(nombre AS INTEGER)), 0)
                FROM Temporadas
                WHERE id_grupo=? AND nombre GLOB '[0-9]*'
            """, (id_grupo,)).fetchone()
            return int(row[0]) + 1 if row and row[0] is not None else 1

        def _crear_nueva():
            n = _next_seq()
            fin = (hoy + timedelta(days=int(dur))) if dur else None
            c.execute("""
                INSERT INTO Temporadas (id_grupo, nombre, fecha_inicio, fecha_fin, duracion_dias, activa)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                id_grupo,
                str(n),                       # 👈 nombre numérico
                hoy.isoformat(),
                fin.isoformat() if fin else None,
                int(dur) if dur else None
            ))
            return c.lastrowid

        if not temp:
            new_id = _crear_nueva()
            conn.commit()
            return new_id

        # ¿Caducada?
        fin = temp["fecha_fin"]
        if fin and date.fromisoformat(fin) <= hoy:
            c.execute("UPDATE Temporadas SET activa=0 WHERE id=?", (temp["id"],))
            new_id = _crear_nueva()
            conn.commit()
            return new_id

        return temp["id"]
