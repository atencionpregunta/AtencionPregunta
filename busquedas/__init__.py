from flask import Blueprint

auth_bp = Blueprint("busquedas", __name__)

from . import routes  # importa las rutas y las registra en el blueprint
