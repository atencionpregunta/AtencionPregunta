import sqlite3
from datetime import datetime

# Conectar a la base de datos
conn = sqlite3.connect("database.db")
conn.execute("PRAGMA foreign_keys = ON;")
cursor = conn.cursor()

# Insertar usuario Iker
usuario_id = 1
cursor.execute(
    "INSERT OR IGNORE INTO Usuarios (id, mail, usuario, contrasena, fec_ini, pais, edad) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (
        usuario_id,
        "iker@example.com",
        "iker",
        "hash1234",  # Idealmente hasheado
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "España",
        28,
    )
)

# Insertar grupo
grupo_id = 1
cursor.execute(
    "INSERT OR IGNORE INTO Grupos (id, fec_ini, codigo, tipo, contrasena) VALUES (?, ?, ?, ?, ?)",
    (
        grupo_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "GRUPOIKER123",
        "privado",
        "grupo123",
    )
)

# Relacionar usuario con el grupo
cursor.execute(
    "INSERT OR IGNORE INTO Grupo_Usuario (id_grupo, id_usuario) VALUES (?, ?)",
    (grupo_id, usuario_id),
)

# Guardar cambios y cerrar
conn.commit()
conn.close()
print("✅ Usuario y grupo creados correctamente.")


