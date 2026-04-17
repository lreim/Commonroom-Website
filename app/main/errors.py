from flask import render_template
from . import main    #heisst: importiere aus dem aktuellen package (hier ist es main, weil main ein init.py hat )
#ich importiere damit das main-blueprint objekt aus dem init.py code

@main.app_errorhandler(404)
def page_not_found(e):
    return render_template("404.html", active_page=None), 404

@main.app_errorhandler(500)   #app_, weil das eine globale Methode von blueprint ist 
def internal_server_error(e):
    return render_template("500.html", active_page=None), 500

