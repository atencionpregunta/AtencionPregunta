#!/usr/bin/env bash
set -euo pipefail

# Ruta del disco persistente que montaste en Render
export DB_PATH="/opt/render/db/database.db"

# Asegurar carpeta del disco
mkdir -p /opt/render/db

# Si no existe la DB en el disco, crearla con tu esquema
if [ ! -f "$DB_PATH" ]; then
  echo ">> Creando database en el Persistent Disk..."
  python init_db.py
else
  echo ">> DB ya existe en el Persistent Disk."
fi

# Arrancar con 1 worker (SQLite)
gunicorn -w 1 -b 0.0.0.0:10000 app:app
