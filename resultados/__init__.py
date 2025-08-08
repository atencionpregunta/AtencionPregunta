from flask import Blueprint

resultados_bp = Blueprint("resultados", __name__)

from . import routes
