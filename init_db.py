import os, sqlite3
from datetime import datetime

DB_PATH = "database.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
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

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_grupos_codigo
        ON Grupos(codigo COLLATE NOCASE);
    """)

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

    # ---------- SEMILLA SI ESTÁ VACÍA ----------
    n = cur.execute("SELECT COUNT(*) FROM Preguntas").fetchone()[0]
    if n == 0:
        datos = [
            {
                "pregunta": "¿En que año se publico el archiconocido album de A.D.R.O.M.I.C.F.M.S.",
                "categoria": "Riverland",
                "dificultad": "difícil",
                "ruta_audio": None,
                "ruta_imagen": "img/1.jpg",
                "respuestas": [("2011",0),("2012",0),("2013",1),("2014",0),("2015",0),("2016",0)]
            },
            {
                "pregunta": "¿Quien le enseño a Nico Miseria Parera que la industria musical era un jardin de puñales?",
                "categoria": "Riverland",
                "dificultad": "difícil",
                "ruta_audio": None,
                "ruta_imagen": None,
                "respuestas": [("Dellafuente",0),("Ill Pekeño",0),("Gata Cattana ",1),("Dano",0),("Alba Calva",0),("Craneo",0),("ToteKing",0)]
            },
            {
                "pregunta": "Cual de los artistas de la cartelera tiene mas oyentes mensuales",
                "categoria": "Riverland",
                "dificultad": "media",
                "ruta_audio": None,
                "ruta_imagen": None,
                "respuestas": [("Yung Beef",0),("Neo Pistea",0),("Pablo Chill-e",1),("Rusowsky",0),("Judeline",0),("NSQK",0),("BB Trikz",0)]
            },
            {
                "pregunta": "¿A que canción pertenece este inicio?",
                "categoria": "Riverland",
                "dificultad": "difícil",
                "ruta_audio": "audio/3.mp3",
                "ruta_imagen": None,
                "respuestas": [
                    ("Cruz Cafuné – “Cosecha",0),
                    ("C. Tangana – “Te Olvidaste” (feat. Omar Apollo)",0),
                    ("Sticky M.A. – “Cola de dragón",0),
                    ("Kinder Malo – “Días Raros”",0),
                    ("rusowsky, Bb trickz - uwu^^",1),
                    ("Recycled J – “Bambino”",0)
                ]
            },
            {
                "pregunta": "¿Quién coño es el este noname de Locoplaya?",
                "categoria": "Riverland",
                "dificultad": "difícil",
                "ruta_audio": None,
                "ruta_imagen": "img/4.jpg",
                "respuestas": [("Drace",0),("Mavé",0),("Uge",1),("Soren",0),("Oven",0),("Zave",0)]
            },
            {
                "pregunta": "¿Cual es el productor de esta cancion?",
                "categoria": "Riverland",
                "dificultad": "difícil",
                "ruta_audio": "audio/5.mp3",
                "ruta_imagen": None,
                "respuestas": [("Steve Lean",0),("Enry-K",1),("Ceo Xander",0),("VH El Virus",0),("Nadddot",0),("Yung Beef",0)]
            },
            {
                "pregunta": "¿Qué artista tiene mayor indice de caos segun el mongolo de ChatGPT?",
                "categoria": "Riverland",
                "dificultad": "media",
                "ruta_audio": None,
                "ruta_imagen": None,
                "respuestas": [("Yung Beef",1),("Ben Yart",0),("Morad",0),("Leiti",0),("Gloosito",0),("Soto Asa",0)]
            },
            {
                "pregunta": "¿De que artista son estos petetitos tan monos?",
                "categoria": "Riverland",
                "dificultad": "media",
                "ruta_audio": None,
                "ruta_imagen": "img/7.jpg",
                "respuestas": [("Judeline",0),("Juicy Bae",0),("Saramalacara",1),("Lorna",0),("BB Trickz ",0),("Verdunch Izquierda",0),("Verdunch Derecha",0)]
            },
            {
                "pregunta": "¿En cuantos conciertos se cantó Rifle Taliban Remix el año pasado?",
                "categoria": "Riverland",
                "dificultad": "media",
                "ruta_audio": None,
                "ruta_imagen": None,
                "respuestas": [("2",0),("3",0),("4",1),("5",0),("6",0),("7",0)]
            },
            {
                "pregunta": "¿Por qué es imposible que Lorna pueda ir al registro a poner 'una' polla a su nombre?",
                "categoria": "Riverland",
                "dificultad": "media",
                "ruta_audio": None,
                "ruta_imagen": None,
                "respuestas": [
                    ("La Ley Hipotecaria solo permite registrar bienes que se encuentren en escritura pública.",0),
                    ("Solo se pueden registrar cosas que no cambien de tamaño con la temperatura.",0),
                    ("La Ley del Notariado impide que se registren bienes que no estén tasados por el Catastro",0),
                    ("El Registro Civil ya no acepta inscripciones de objetos menores de 30 cm",0),
                    ("sería tratarla como un bien patrimonial, algo que la ley prohíbe para proteger la dignidad y la integridad de la persona.",1)
                ]
            }
        ]

        for item in datos:
            cur.execute("""
                INSERT INTO Preguntas
                (pregunta, categoria, dificultad, fecha_creacion, fecha_mostrada, ruta_audio, ruta_imagen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item["pregunta"],
                item["categoria"],
                item["dificultad"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                None,
                item["ruta_audio"],
                item["ruta_imagen"]
            ))
            id_pregunta = cur.lastrowid
            for resp, correcta in item["respuestas"]:
                cur.execute("""
                    INSERT INTO Respuestas (id_pregunta, respuesta, correcta)
                    VALUES (?, ?, ?)
                """, (id_pregunta, resp, correcta))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada y sembrada si estaba vacía:", DB_PATH)
