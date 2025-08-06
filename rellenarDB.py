import sqlite3
import random
from datetime import datetime, timedelta

def rellenar_bd():
    conn = sqlite3.connect("database.db")
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    categorias = ["Historia", "Ciencia", "Geografía", "Deportes", "Arte", "Cultura general"]
    dificultades = ["Fácil", "Media", "Difícil"]

    for i in range(1, 101):
        pregunta_texto = f"¿Cuál es la respuesta correcta a la pregunta número {i}?"
        categoria = random.choice(categorias)
        dificultad = random.choice(dificultades)
        fecha_creacion = (datetime.now() - timedelta(days=random.randint(0, 1000))).strftime("%Y-%m-%d %H:%M:%S")

        # Insertar pregunta
        cursor.execute('''
            INSERT INTO Preguntas (id, pregunta, categoria, dificultad, fecha_creacion)
            VALUES (?, ?, ?, ?, ?)
        ''', (i, pregunta_texto, categoria, dificultad, fecha_creacion))

        # Insertar respuestas
        correcta = random.randint(1, 4)
        for j in range(1, 5):
            respuesta_texto = f"Opción {j} para pregunta {i}"
            es_correcta = int(j == correcta)  # SQLite usa 0/1 para booleanos
            respuesta_id = (i - 1) * 4 + j

            cursor.execute('''
                INSERT INTO Respuestas (id, id_pregunta, respuesta, correcta)
                VALUES (?, ?, ?, ?)
            ''', (respuesta_id, i, respuesta_texto, es_correcta))

    conn.commit()
    conn.close()
    print("Base de datos rellenada con 100 preguntas y respuestas.")

if __name__ == "__main__":
    rellenar_bd()
import sqlite3
import random
from datetime import datetime, timedelta

def rellenar_bd():
    conn = sqlite3.connect("database.db")
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    categorias = ["Historia", "Ciencia", "Geografía", "Deportes", "Arte", "Cultura general"]
    dificultades = ["Fácil", "Media", "Difícil"]

    for i in range(1, 101):
        pregunta_texto = f"¿Cuál es la respuesta correcta a la pregunta número {i}?"
        categoria = random.choice(categorias)
        dificultad = random.choice(dificultades)
        fecha_creacion = (datetime.now() - timedelta(days=random.randint(0, 1000))).strftime("%Y-%m-%d %H:%M:%S")

        # Insertar pregunta
        cursor.execute('''
            INSERT INTO Preguntas (id, pregunta, categoria, dificultad, fecha_creacion)
            VALUES (?, ?, ?, ?, ?)
        ''', (i, pregunta_texto, categoria, dificultad, fecha_creacion))

        # Insertar respuestas
        correcta = random.randint(1, 4)
        for j in range(1, 5):
            respuesta_texto = f"Opción {j} para pregunta {i}"
            es_correcta = int(j == correcta)  # SQLite usa 0/1 para booleanos
            respuesta_id = (i - 1) * 4 + j

            cursor.execute('''
                INSERT INTO Respuestas (id, id_pregunta, respuesta, correcta)
                VALUES (?, ?, ?, ?)
            ''', (respuesta_id, i, respuesta_texto, es_correcta))

    conn.commit()
    conn.close()
    print("Base de datos rellenada con 100 preguntas y respuestas.")

if __name__ == "__main__":
    rellenar_bd()
