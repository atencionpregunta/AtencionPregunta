import sqlite3
import re
from pathlib import Path

DB_PATH = "database.db"
SQL_PATH = "riverland_150_preguntas.sql"  # pon aquí tu ruta real

# Regex para extraer cada bloque:
# 1) una línea INSERT INTO Preguntas (...)
# 2) seguido de varias líneas INSERT INTO Respuestas (...) VALUES (last_insert_rowid(), '...', X);
re_preg = re.compile(
    r"INSERT\s+INTO\s+Preguntas\s*\(\s*pregunta\s*\)\s*VALUES\s*\(\s*'(?P<pregunta>.*?)'\s*\)\s*;",
    re.IGNORECASE | re.DOTALL
)
re_resp = re.compile(
    r"INSERT\s+INTO\s+Respuestas\s*\(\s*id_pregunta\s*,\s*respuesta\s*,\s*correcta\s*\)\s*"
    r"VALUES\s*\(\s*last_insert_rowid\(\)\s*,\s*'(?P<resp>.*?)'\s*,\s*(?P<corr>[01])\s*\)\s*;",
    re.IGNORECASE | re.DOTALL
)

def parse_blocks(sql_text: str):
    """Devuelve lista de (pregunta, [(respuesta, correcta), ...]) preservando el orden."""
    pos = 0
    blocks = []
    while True:
        m_q = re_preg.search(sql_text, pos)
        if not m_q:
            break
        pregunta = m_q.group("pregunta").replace("''", "'")  # des-escapar para python
        start_resp = m_q.end()
        # Las respuestas son las siguientes líneas hasta la próxima pregunta o fin
        m_next_q = re_preg.search(sql_text, start_resp)
        end_resp = m_next_q.start() if m_next_q else len(sql_text)
        resp_text = sql_text[start_resp:end_resp]

        respuestas = []
        for m_r in re_resp.finditer(resp_text):
            resp = m_r.group("resp").replace("''", "'")
            corr = int(m_r.group("corr"))
            respuestas.append((resp, corr))

        if not respuestas:
            raise ValueError(f"La pregunta [{pregunta}] no tiene respuestas detectadas.")

        blocks.append((pregunta, respuestas))
        pos = end_resp
    return blocks

def main():
    sql_path = Path(SQL_PATH)
    if not sql_path.exists():
        raise FileNotFoundError(f"No encuentro {sql_path.resolve()}")

    sql_text = sql_path.read_text(encoding="utf-8")

    blocks = parse_blocks(sql_text)
    print(f"Detectadas {len(blocks)} preguntas en el SQL.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    try:
        cur.execute("BEGIN")
        for i, (pregunta, respuestas) in enumerate(blocks, start=1):
            # Evitar duplicados por texto de pregunta (opcional)
            cur.execute("SELECT id FROM Preguntas WHERE pregunta = ?", (pregunta,))
            row = cur.fetchone()
            if row:
                pregunta_id = row[0]
            else:
                cur.execute("INSERT INTO Preguntas (pregunta) VALUES (?)", (pregunta,))
                pregunta_id = cur.lastrowid

            # Inserta respuestas (borra previas si existían para esta pregunta, opcional)
            # cur.execute("DELETE FROM Respuestas WHERE id_pregunta = ?", (pregunta_id,))
            for resp, corr in respuestas:
                cur.execute(
                    "INSERT INTO Respuestas (id_pregunta, respuesta, correcta) VALUES (?, ?, ?)",
                    (pregunta_id, resp, corr)
                )
            if i % 10 == 0:
                print(f"  • Insertadas {i} preguntas...")
        conn.commit()
        print("✅ Importación completada.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
