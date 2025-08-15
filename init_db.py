import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/opt/render/db/database.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    cursor = conn.cursor()

    cursor.execute("""
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Grupos (
            id INTEGER PRIMARY KEY,
            fec_ini DATETIME,
            codigo TEXT,
            tipo TEXT,
            contrasena TEXT
        );
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_grupos_codigo
        ON Grupos(codigo COLLATE NOCASE);
    """)

    cursor.execute("""
       CREATE TABLE IF NOT EXISTS grupo_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_grupo INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL,
            UNIQUE(id_grupo, id_usuario),
            FOREIGN KEY (id_grupo) REFERENCES Grupos(id) ON DELETE CASCADE,
            FOREIGN KEY (id_usuario) REFERENCES Usuarios(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Respuestas (
            id INTEGER PRIMARY KEY,
            id_pregunta INTEGER,
            respuesta TEXT,
            correcta BOOLEAN,
            FOREIGN KEY (id_pregunta) REFERENCES Preguntas(id) ON DELETE CASCADE
        );
    """)

    # Insertar fila especial [TIMEOUT] solo si no existe
    cursor.execute("""
        INSERT OR IGNORE INTO Respuestas (id, id_pregunta, respuesta, correcta)
        VALUES (0, NULL, '[TIMEOUT]', 0);
    """)

    cursor.execute("""
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
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada en", DB_PATH)
