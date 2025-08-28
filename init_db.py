import os, sqlite3, csv
from contextlib import closing
from datetime import datetime

# Ruta de BD (variable en Render → Environment, con fallback local)
DB_PATH = "/opt/render/db/database.db"

# CSVs (subidos en tu repo)
# Pon los CSV en: /opt/render/project/src/data/...
PREGUNTAS_CSV = "Chat_de_WhatsApp_con_ATENCION_PREGUNTA_preguntas.csv"
RESPUESTAS_CSV = "Chat_de_WhatsApp_con_ATENCION_PREGUNTA_respuestas.csv"

# Fallbacks locales para trabajar en tu PC sin tocar nada:
if not os.path.exists(PREGUNTAS_CSV):
    PREGUNTAS_CSV = "data/whatsapp_chat_preguntas.csv"
if not os.path.exists(RESPUESTAS_CSV):
    RESPUESTAS_CSV = "data/whatsapp_chat_respuestas.csv"

# -------------------- Helpers --------------------
def ensure_db_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
            edad INTEGER
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Grupos (
            id INTEGER PRIMARY KEY,
            fec_ini DATETIME,
            codigo TEXT,
            tipo TEXT,
            contrasena TEXT
        );
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
        CREATE TABLE IF NOT EXISTS Resultados (
            fecha DATETIME,
            id_usuario INTEGER,
            id_grupo INTEGER,
            temporada TEXT,
            puntuacion INTEGER,
            correcta BOOLEAN,
            id_pregunta INTEGER,
            id_respuesta INTEGER,
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
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
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
        # Preguntas
        for row in _leer_csv(preguntas_csv, preguntas_cols):
            cur.execute("""
                INSERT OR REPLACE INTO Preguntas
                (id, pregunta, categoria, dificultad, fecha_creacion, fecha_mostrada, ruta_audio, ruta_imagen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(row["id"]) if row["id"] else None,
                row["pregunta"],
                row.get("categoria") or None,
                row.get("dificultad") or None,
                row.get("fecha_creacion") or None,
                row.get("fecha_mostrada") or None,
                row.get("ruta_audio") or None,
                row.get("ruta_imagen") or None
            ))
        # Respuestas
        for row in _leer_csv(respuestas_csv, respuestas_cols):
            cur.execute("""
                INSERT OR REPLACE INTO Respuestas
                (id, id_pregunta, respuesta, correcta)
                VALUES (?, ?, ?, ?)
            """, (
                int(row["id"]) if row["id"] else None,
                int(row["id_pregunta"]),
                row["respuesta"],
                _to_int_bool(row.get("correcta"))
            ))

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
            # Si aún no has subido los CSV al repo, no rompemos el arranque:
            print(f"⚠ No se importaron CSV: {e}")

if __name__ == "__main__":
    bootstrap_db()
    print(f"BD lista en: {DB_PATH}")