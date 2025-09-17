# utils.py
from __future__ import annotations
from datetime import datetime, timedelta, time, date
from zoneinfo import ZoneInfo
import sqlite3
from functools import wraps
from flask import session, redirect, url_for, flash

from db import get_conn, db_lock

# =========================
# Zona horaria y jornada 09→09
# =========================
TZ = ZoneInfo("Europe/Madrid")
HORA_SELECCION = time(9, 0, 0)  # 09:00

def ahora_local() -> datetime:
    return datetime.now(TZ)

def ahora_local_str() -> str:
    return ahora_local().strftime("%Y-%m-%d %H:%M:%S")

def hoy_local_str() -> str:
    return ahora_local().date().isoformat()

def jornada_bounds(ref: datetime | None = None):
    """
    Devuelve (ini, fin, etiqueta, weekday) de la JORNADA 09:00→09:00 que contiene 'ref'.
    - ini, fin: strings "YYYY-MM-DD HH:MM:SS" en hora local [ini, fin)
    - etiqueta: "YYYY-MM-DD" (fecha del INICIO 09:00)
    - weekday: 0..6 del INICIO (Mon=0, Sun=6)
    """
    ref = ref or ahora_local()
    corte_hoy = ref.replace(hour=HORA_SELECCION.hour, minute=HORA_SELECCION.minute,
                            second=0, microsecond=0)
    if ref >= corte_hoy:
        ini_dt = corte_hoy
    else:
        ini_dt = corte_hoy - timedelta(days=1)
    fin_dt = ini_dt + timedelta(days=1)
    return (
        ini_dt.strftime("%Y-%m-%d %H:%M:%S"),
        fin_dt.strftime("%Y-%m-%d %H:%M:%S"),
        ini_dt.date().isoformat(),
        ini_dt.weekday(),
    )

def es_domingo() -> bool:
    # Domingo según la JORNADA (no el calendario puro)
    _, _, _, wd = jornada_bounds()
    return wd == 6

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
        conn.row_factory = sqlite3.Row
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
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT G.id
            FROM Grupos G
            JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
            WHERE GU.id_usuario = ?
            ORDER BY G.codigo
        """, (usuario_id,))
        rows = cur.fetchall()
        return [int(r["id"]) for r in rows]

def get_grupos_usuario(usuario_id: int) -> list[dict]:
    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT G.id, G.codigo
            FROM Grupos G
            JOIN Grupo_Usuario GU ON G.id = GU.id_grupo
            WHERE GU.id_usuario = ?
            ORDER BY G.codigo
        """, (usuario_id,))
        rows = cur.fetchall()
        return [dict(id=int(r["id"]), codigo=r["codigo"]) for r in rows]

# =========================
# Puntuaciones
# =========================
def get_puntuacion_anterior(id_usuario: int, id_grupo: int) -> int | None:
    """
    Devuelve la ÚLTIMA puntuación registrada (no el máximo histórico).
    """
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
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
# Temporadas
# =========================
def ensure_active_temporada(id_grupo: int):
    """
    Devuelve el ID de la temporada activa del grupo.
    - Si no hay activa → crea temporada con nombre numérico incremental ("1","2",...).
    - Si hay activa y está caducada → la cierra y crea otra con el siguiente número.
    - Si hay activa y no está caducada → devuelve su id tal cual.
    """
    def _hoy() -> date:
        return datetime.now(TZ).date()

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        g = c.execute(
            "SELECT duracion_temp FROM Grupos WHERE id=?",
            (id_grupo,)
        ).fetchone()
        if not g:
            return None

        dur = g["duracion_temp"]  # puede ser None
        hoy = _hoy()

        temp = c.execute(
            "SELECT * FROM Temporadas WHERE id_grupo=? AND activa=1 LIMIT 1",
            (id_grupo,)
        ).fetchone()

        def _next_seq() -> int:
            row = c.execute("""
                SELECT COALESCE(MAX(CAST(nombre AS INTEGER)), 0)
                FROM Temporadas
                WHERE id_grupo=? AND nombre GLOB '[0-9]*'
            """, (id_grupo,)).fetchone()
            return (int(row[0]) + 1) if row and row[0] is not None else 1

        def _crear_nueva():
            n = _next_seq()
            fin = (hoy + timedelta(days=int(dur))) if dur else None
            c.execute("""
                INSERT INTO Temporadas (id_grupo, nombre, fecha_inicio, fecha_fin, duracion_dias, activa)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                id_grupo,
                str(n),
                hoy.isoformat(),
                fin.isoformat() if fin else None,
                int(dur) if dur else None
            ))
            return c.lastrowid

        if not temp:
            new_id = _crear_nueva()
            conn.commit()
            return new_id

        fin = temp["fecha_fin"]
        if fin and date.fromisoformat(fin) <= hoy:
            c.execute("UPDATE Temporadas SET activa=0 WHERE id=?", (temp["id"],))
            new_id = _crear_nueva()
            conn.commit()
            return new_id

        return temp["id"]

def dias_temporada_restantes(id_grupo: int):
    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        t = c.execute(
            "SELECT fecha_fin FROM Temporadas WHERE id_grupo=? AND activa=1 LIMIT 1",
            (id_grupo,)
        ).fetchone()
    if not t or not t["fecha_fin"]:
        return None
    hoy = datetime.now(TZ).date()
    fin = date.fromisoformat(t["fecha_fin"])
    return max(0, (fin - hoy).days)

# =========================
# Pregunta del día (NO-Relámpago, atómica por jornada 09→09)
# =========================
def get_pregunta_del_dia():
    """
    Devuelve (pregunta_dict, respuestas_list) para la jornada actual (09→09).
    Publica UNA (marca fecha_mostrada) de forma atómica si no hubiera.
    Excluye tipo='Relampago'.
    """
    ref = ahora_local()
    j_ini, j_fin, _, _ = jornada_bounds(ref)

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")

        # 1) ¿Ya hay publicada en esta jornada?
        c.execute("""
            SELECT * FROM Preguntas
            WHERE COALESCE(tipo,'') <> 'Relampago'
              AND datetime(fecha_mostrada) >= ?
              AND datetime(fecha_mostrada) <  ?
            ORDER BY datetime(fecha_mostrada) ASC, id ASC
            LIMIT 1
        """, (j_ini, j_fin))
        pregunta = c.fetchone()

        # 2) Si no hay y ya hemos pasado el corte → publicar 1 (atómico)
        if not pregunta and ref.strftime("%Y-%m-%d %H:%M:%S") >= j_ini:
            try:
                c.execute("BEGIN IMMEDIATE")

                c.execute("""
                    SELECT * FROM Preguntas
                    WHERE COALESCE(tipo,'') <> 'Relampago'
                      AND datetime(fecha_mostrada) >= ?
                      AND datetime(fecha_mostrada) <  ?
                    ORDER BY datetime(fecha_mostrada) ASC, id ASC
                    LIMIT 1
                """, (j_ini, j_fin))
                pregunta = c.fetchone()

                if not pregunta:
                    c.execute("""
                        SELECT * FROM Preguntas
                        WHERE COALESCE(tipo,'') <> 'Relampago'
                          AND (fecha_mostrada IS NULL
                               OR datetime(fecha_mostrada) < ?
                               OR datetime(fecha_mostrada) >= ?)
                        ORDER BY (fecha_mostrada IS NOT NULL),
                                 datetime(fecha_mostrada) ASC,
                                 id ASC
                        LIMIT 1
                    """, (j_ini, j_fin))
                    cand = c.fetchone()
                    if cand:
                        c.execute(
                            "UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?",
                            (ref.strftime("%Y-%m-%d %H:%M:%S"), cand["id"])
                        )
                        pregunta = cand

                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                c.execute("""
                    SELECT * FROM Preguntas
                    WHERE COALESCE(tipo,'') <> 'Relampago'
                      AND datetime(fecha_mostrada) >= ?
                      AND datetime(fecha_mostrada) <  ?
                    ORDER BY datetime(fecha_mostrada) ASC, id ASC
                    LIMIT 1
                """, (j_ini, j_fin))
                pregunta = c.fetchone()

        # 3) Fallback: última NO-Relámpago publicada antes de ahora
        if not pregunta:
            c.execute("""
                SELECT * FROM Preguntas
                WHERE COALESCE(tipo,'') <> 'Relampago'
                  AND fecha_mostrada IS NOT NULL
                  AND datetime(fecha_mostrada) <= ?
                ORDER BY datetime(fecha_mostrada) DESC, id DESC
                LIMIT 1
            """, (ref.strftime("%Y-%m-%d %H:%M:%S"),))
            pregunta = c.fetchone()

        if not pregunta:
            return None, []

        # Respuestas
        c.execute("""
            SELECT id, respuesta, correcta
            FROM Respuestas
            WHERE id_pregunta = ?
            ORDER BY id
        """, (pregunta["id"],))
        respuestas = c.fetchall()

        return dict(pregunta), [dict(r) for r in respuestas]

# =========================
# Pack Relámpago (domingo)
# =========================
def ensure_pack_relampago_hoy(limit: int = 3) -> list[dict]:
    ref = ahora_local()
    j_ini, j_fin, _, _ = jornada_bounds(ref)

    with db_lock, get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")

        c.execute("""
            SELECT *
            FROM Preguntas
            WHERE tipo = 'Relampago'
              AND datetime(fecha_mostrada) >= ?
              AND datetime(fecha_mostrada) <  ?
            ORDER BY datetime(fecha_mostrada) ASC, id ASC
        """, (j_ini, j_fin))
        pack = c.fetchall()

        if len(pack) < limit and ref.strftime("%Y-%m-%d %H:%M:%S") >= j_ini:
            try:
                c.execute("BEGIN IMMEDIATE")
                c.execute("""
                    SELECT *
                    FROM Preguntas
                    WHERE tipo = 'Relampago'
                      AND datetime(fecha_mostrada) >= ?
                      AND datetime(fecha_mostrada) <  ?
                    ORDER BY datetime(fecha_mostrada) ASC, id ASC
                """, (j_ini, j_fin))
                pack = c.fetchall()

                if len(pack) < limit:
                    faltan = limit - len(pack)
                    c.execute("""
                        SELECT *
                        FROM Preguntas
                        WHERE tipo = 'Relampago'
                          AND (fecha_mostrada IS NULL
                               OR datetime(fecha_mostrada) < ?
                               OR datetime(fecha_mostrada) >= ?)
                        ORDER BY (fecha_mostrada IS NOT NULL),
                                 datetime(fecha_mostrada) ASC,
                                 id ASC
                        LIMIT ?
                    """, (j_ini, j_fin, faltan))
                    nuevos = c.fetchall()

                    base = ahora_local()
                    for i, row in enumerate(nuevos):
                        ts = (base + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
                        c.execute("UPDATE Preguntas SET fecha_mostrada = ? WHERE id = ?", (ts, row["id"]))

                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()

            c.execute("""
                SELECT *
                FROM Preguntas
                WHERE tipo = 'Relampago'
                  AND datetime(fecha_mostrada) >= ?
                  AND datetime(fecha_mostrada) <  ?
                ORDER BY datetime(fecha_mostrada) ASC, id ASC
            """, (j_ini, j_fin))
            pack = c.fetchall()

        return [dict(r) for r in pack]

# =========================
# Migraciones de esquema
# =========================
def ensure_schema_usuarios():
    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(Usuarios)")
        cols = {row[1].lower() for row in cur.fetchall()}
        # aquí puedes añadir alter table si quieres nuevas columnas
        conn.commit()

# =========================
# Índices recomendados
# =========================
def ensure_indices_recomendados():
    with db_lock, get_conn() as conn:
        c = conn.cursor()
        # Una sola NO-Relampago por jornada (09→09)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_preg_no_rel_jornada
            ON Preguntas (DATE(fecha_mostrada, '-9 hours'))
            WHERE COALESCE(tipo,'') <> 'Relampago';
        """)
        # Índices de apoyo
        c.execute("CREATE INDEX IF NOT EXISTS ix_preguntas_fecha ON Preguntas(datetime(fecha_mostrada));")
        c.execute("CREATE INDEX IF NOT EXISTS ix_resultados_usuario_fecha ON Resultados(id_usuario, datetime(fecha));")
        conn.commit()
