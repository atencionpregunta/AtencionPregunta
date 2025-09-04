from flask import Blueprint

# Nombre del blueprint = "chat" (así usas url_for('chat.ver_chat', ...))
chat_bp = Blueprint("chat", __name__)

from . import routes  # noqa: F401
