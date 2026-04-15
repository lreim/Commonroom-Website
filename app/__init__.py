from flask import Flask
from flask_bootstrap import Bootstrap
from config import config

bootstrap = Bootstrap()


#Application factory: erzeugt jedes Mal neu konfiguierte Flask-App 
#je nachdem, was für (config_name) eingesetzt wird und aufgerufen wird, wier app verschieden konfiguriert 
def create_app(config_name):
    app = Flask(__name__)     #erzeugt Flask-Objekt 
    app.config.from_object(config[config_name])   #lädt alle Variablen des dictioaries abhängig vom fkt argument am Anfang 
    config[config_name].init_app(app)   #??

    #extensions an app binden, statt nur wie oben zu definieren 
    bootstrap.init_app(app)
    

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)   #hängt alle Routen an die App

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix="/auth")

    return app
