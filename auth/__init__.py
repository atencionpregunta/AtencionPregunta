from flask import Blueprint

auth_bp = Blueprint("auth", __name__)

from . import routes  # importa las rutas y las registra en el blueprint
