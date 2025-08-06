import sqlite3
from datetime import datetime

def insertar_ejemplo():
    conn = sqlite3.connect("database.db")
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    preguntas = [
        {
            "pregunta": "¿Cuál es la capital de Francia?",
            "categoria": "Geografía",
            "dificultad": "Fácil",
            "fecha_creacion": "2025-08-06",
            "respuestas": [
                ("Madrid", 0),
                ("Roma", 0),
                ("París", 1),
                ("Berlín", 0)
            ]
        },
        {
            "pregunta": "¿Quién escribió 'Cien años de soledad'?",
            "categoria": "Cultura general",
            "dificultad": "Media",
            "fecha_creacion": "2025-08-06",
            "respuestas": [
                ("Pablo Neruda", 0),
                ("Gabriel García Márquez", 1),
                ("Mario Vargas Llosa", 0),
                ("Julio Cortázar", 0)
            ]
        },
        {
            "pregunta": "¿Cuál es el resultado de 9 × 8?",
            "categoria": "Ciencia",
            "dificultad": "Fácil",
            "fecha_creacion": "2025-08-06",
            "respuestas": [
                ("72", 1),
                ("64", 0),
                ("81", 0),
                ("96", 0)
            ]
        }
    ]

    for p in preguntas:
        cursor.execute("""
            INSERT INTO Preguntas (pregunta, categoria, dificultad, fecha_creacion)
            VALUES (?, ?, ?, ?)
        """, (p["pregunta"], p["categoria"], p["dificultad"], p["fecha_creacion"]))
        id_pregunta = cursor.lastrowid

        for respuesta, correcta in p["respuestas"]:
            cursor.execute("""
                INSERT INTO Respuestas (id_pregunta, respuesta, correcta)
                VALUES (?, ?, ?)
            """, (id_pregunta, respuesta, correcta))

    conn.commit()
    conn.close()
    print("✅ Preguntas y respuestas de ejemplo insertadas.")

insertar_ejemplo()
