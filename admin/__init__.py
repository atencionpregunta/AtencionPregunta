from flask import Blueprint

resultados_bp = Blueprint("admin", __name__)

from . import routes