import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Usuarios (
            id INTEGER PRIMARY KEY,
            mail TEXT UNIQUE,
            usuario TEXT,
            contrasena TEXT,
            fec_ini DATETIME,
            pais TEXT,
            edad INTEGER
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Grupos (
            id INTEGER PRIMARY KEY,
            fec_ini DATETIME,
            codigo TEXT,
            tipo TEXT,
            contrasena TEXT
        );
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Grupo_Usuario (
            id_grupo INTEGER,
            id_usuario INTEGER,
            PRIMARY KEY (id_grupo, id_usuario),
            FOREIGN KEY (id_grupo) REFERENCES Grupos(id),
            FOREIGN KEY (id_usuario) REFERENCES Usuarios(id)
        );
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Preguntas (
            id INTEGER PRIMARY KEY,
            pregunta TEXT,
            categoria TEXT,
            dificultad TEXT,
            fecha_creacion DATETIME
        );

    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Respuestas (
            id INTEGER PRIMARY KEY,
            id_pregunta INTEGER,
            respuesta TEXT,
            correcta BOOLEAN,
            FOREIGN KEY (id_pregunta) REFERENCES Preguntas(id)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Resultados (
            fecha DATETIME,
            id_usuario INTEGER,
            id_grupo INTEGER,
            temporada TEXT,
            id_pregunta INTEGER,
            id_respuesta INTEGER,
            puntuacion INTEGER,
            FOREIGN KEY (id_usuario) REFERENCES Usuarios(id),
            FOREIGN KEY (id_grupo) REFERENCES Grupos(id),
            FOREIGN KEY (id_pregunta) REFERENCES Preguntas(id),
            FOREIGN KEY (id_respuesta) REFERENCES Respuestas(id)
        );
    ''')


    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada.")
