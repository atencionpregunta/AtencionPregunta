# admin/__init__.py
from flask import Blueprint

admin_bp = Blueprint("admin", __name__)  # <-- se define aquí UNA sola vez

# Importa las rutas para que se registren en este blueprint
from . import routes  # noqa
