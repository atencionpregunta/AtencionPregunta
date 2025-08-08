from flask import Blueprint

grupos_bp = Blueprint("grupos", __name__)

from . import routes  # importa las rutas y las registra en el blueprint
