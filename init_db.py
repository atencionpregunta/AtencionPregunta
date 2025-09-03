import os, sqlite3, csv
from contextlib import closing
from datetime import datetime
from pathlib import Path

def _as_int(val, default=None):
    if val is None:
        return default
    s = str(val).strip()
    if s == "":
        return default
    try:
        return int(s)
    except Exception:
        return default

# ----- Rutas robustas -----

DB_PATH = os.getenv("DB_PATH", str("database.db"))  # BD en la carpeta del proyecto

# CSVs (absolutos)
PREGUNTAS_CSV = os.getenv("PREGUNTAS_CSV", str("PreguntasPrueba.csv"))
RESPUESTAS_CSV = os.getenv("RESPUESTAS_CSV", str("RespuestasPrueba.csv"))

# -------------------- Helpers --------------------
def ensure_db_dir():
    folder = os.path.dirname(DB_PATH)
    # Solo crear si hay un directorio explícito (no "", no ".")
    if folder and folder not in (".", ""):
        os.makedirs(folder, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def create_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Usuarios (
            id INTEGER PRIMARY KEY,
            mail TEXT UNIQUE,
            usuario TEXT,
            contrasena TEXT,
            fec_ini DATETIME,
            pais TEXT,
            edad INTEGER,
            remember_token TEXT,          
            remember_expira TEXT           
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Grupos (
            id INTEGER PRIMARY KEY,
            fec_ini DATETIME,
            duracion_temp INTEGER,
            codigo TEXT,
            tipo TEXT,
            contrasena TEXT
        );
    """)

    cur.execute("""
        INSERT OR IGNORE INTO Grupos (id, fec_ini, duracion_temp, codigo, tipo, contrasena)
        VALUES (0, NULL, NULL, 'General', 'General', NULL);
    """) 

    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_grupos_codigo ON Grupos(codigo COLLATE NOCASE);""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupo_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_grupo INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL,
            UNIQUE(id_grupo, id_usuario),
            FOREIGN KEY (id_grupo) REFERENCES Grupos(id) ON DELETE CASCADE,
            FOREIGN KEY (id_usuario) REFERENCES Usuarios(id) ON DELETE CASCADE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Preguntas (
            id INTEGER PRIMARY KEY,
            pregunta TEXT,
            categoria TEXT,
            dificultad TEXT,
            fecha_creacion DATETIME,
            fecha_mostrada DATE,
            ruta_audio TEXT,
            ruta_imagen TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Respuestas (
            id INTEGER PRIMARY KEY,
            id_pregunta INTEGER,
            respuesta TEXT,
            correcta BOOLEAN,
            FOREIGN KEY (id_pregunta) REFERENCES Preguntas(id) ON DELETE CASCADE
        );
    """)

    cur.execute("""
        INSERT OR IGNORE INTO Respuestas (id, id_pregunta, respuesta, correcta)
        VALUES (0, NULL, '[TIMEOUT]', 0);
    """)
    
    cur.execute("""
        INSERT OR IGNORE INTO Respuestas (id, id_pregunta, respuesta, correcta)
        VALUES (-1, NULL, '[MULTIPLE]', 0);
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS Resultados (
            fecha DATETIME,
            id_usuario INTEGER,
            id_grupo INTEGER,
            temporada TEXT,
            puntuacion INTEGER,
            correcta BOOLEAN,
            id_pregunta INTEGER,
            id_respuesta INT,
            seleccion_respuestas TEXT,
            FOREIGN KEY (id_usuario) REFERENCES Usuarios(id),
            FOREIGN KEY (id_grupo) REFERENCES Grupos(id),
            FOREIGN KEY (id_pregunta) REFERENCES Preguntas(id),
            FOREIGN KEY (id_respuesta) REFERENCES Respuestas(id)
        );
    """)
    conn.commit()

def tabla_vacia(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0

def _to_int_bool(x) -> int:
    if x is None: return 0
    s = str(x).strip().lower()
    if s in ("1","true","t","yes","y","si","sí","verdadero"): return 1
    if s in ("0","false","f","no","n","falso",""): return 0
    try:
        return 1 if int(s) != 0 else 0
    except Exception:
        return 0

def _leer_csv(path, expected_fields):
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el CSV: {path}")
    with open(path, "r", newline="", encoding="cp1252") as f:
        r = csv.DictReader(f, delimiter=";")  # tu script usa ';' + UTF-8 BOM
        faltan = [c for c in expected_fields if c not in r.fieldnames]
        if faltan:
            raise ValueError(f"CSV {path} sin columnas requeridas: {faltan}. Tiene: {r.fieldnames}")
        for row in r:
            yield row

def importar_csvs(conn: sqlite3.Connection, preguntas_csv: str, respuestas_csv: str):
    preguntas_cols = ["id","pregunta","categoria","dificultad","fecha_creacion","fecha_mostrada","ruta_audio","ruta_imagen"]
    respuestas_cols = ["id","id_pregunta","respuesta","correcta"]

    cur = conn.cursor()
    with conn:
        # --- Preguntas ---
        for row in _leer_csv(preguntas_csv, preguntas_cols):
            pid = _as_int(row.get("id"))
            pregunta_txt = (row.get("pregunta") or "").strip()
            if not pregunta_txt:
                print(f"⚠ Saltando pregunta sin texto (id={pid}): {row}")
                continue

            cur.execute("""
                INSERT OR REPLACE INTO Preguntas
                (id, pregunta, categoria, dificultad, fecha_creacion, fecha_mostrada, ruta_audio, ruta_imagen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pid,
                pregunta_txt,
                (row.get("categoria") or None),
                (row.get("dificultad") or None),
                (row.get("fecha_creacion") or None),
                (row.get("fecha_mostrada") or None),
                (row.get("ruta_audio") or None),
                (row.get("ruta_imagen") or None)
            ))

        # --- Respuestas ---
        for row in _leer_csv(respuestas_csv, respuestas_cols):
            rid = _as_int(row.get("id"))
            pid = _as_int(row.get("id_pregunta"))  # <- puede venir vacío en tu CSV
            respuesta_txt = (row.get("respuesta") or "").strip()
            correcta_val = _to_int_bool(row.get("correcta"))

            # Saltar filas inválidas
            if pid is None:
                # típico: fila TIMEOUT o líneas en blanco al final
                print(f"⚠ Saltando respuesta sin id_pregunta (id={rid}): {row}")
                continue
            if not respuesta_txt:
                print(f"⚠ Saltando respuesta vacía (id={rid}, id_pregunta={pid})")
                continue

            cur.execute("""
                INSERT OR REPLACE INTO Respuestas
                (id, id_pregunta, respuesta, correcta)
                VALUES (?, ?, ?, ?)
            """, (rid, pid, respuesta_txt, correcta_val))


def bootstrap_db():
    ensure_db_dir()
    with closing(get_conn()) as conn:
        create_schema(conn)
        try:
            if tabla_vacia(conn, "Preguntas"):
                importar_csvs(conn, PREGUNTAS_CSV, RESPUESTAS_CSV)
                print("✔ BD inicializada desde CSVs.")
            else:
                print("ℹ BD ya tenía datos. No se importó nada.")
        except FileNotFoundError as e:
            print(f"⚠ No se importaron CSV: {e}")

if __name__ == "__main__":
    bootstrap_db()
    print(f"BD lista en: {DB_PATH}")
