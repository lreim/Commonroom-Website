from flask import Blueprint

main = Blueprint('main', __name__) #erstellt Blueprint Objekt 'main'

from . import views, errors     #guckt im gleichen Ordner (Main) nach, deswegen nur ein Punkt
from ..models import Permission

@main.app_context_processor
def inject_permissions():
    return dict(Permission=Permission)