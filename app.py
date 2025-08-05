# app.py
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import date

app = Flask(__name__)

# Conexión a la base de datos SQLite
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Crear tabla si no existe
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            usuario TEXT,
            aceptada INTEGER
        );
    ''')
    conn.commit()
    conn.close()

@app.route("/")
def pregunta():
    return render_template("index.html", pregunta="¿Aceptas el reto de hoy?")

@app.route("/aceptar", methods=["POST"])
def aceptar():
    conn = get_db_connection()
    conn.execute("INSERT INTO respuestas (fecha, usuario, aceptada) VALUES (?, ?, ?)",
                 (date.today().isoformat(), "usuario_demo", 1))
    conn.commit()
    conn.close()
    return redirect(url_for("pregunta"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
