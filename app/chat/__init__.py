from flask import Blueprint

chat = Blueprint("chat", __name__)

from . import views  # noqa: E402,F401
