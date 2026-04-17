from flask import Flask, render_template
from flask_bootstrap import Bootstrap
from config import config
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy


bootstrap = Bootstrap()
db = SQLAlchemy()
migrate = Migrate()

login_manager = LoginManager()
login_manager.login_view = 'auth.login'      #endpoint for the login page 
login_manager.session_protection = 'strong'


#Application factory: erzeugt jedes Mal neu konfiguierte Flask-App 
#je nachdem, was für (config_name) eingesetzt wird und aufgerufen wird, wier app verschieden konfiguriert 
def create_app(config_name):
    app = Flask(__name__)     #erzeugt Flask-Objekt 
    app.config.from_object(config[config_name])   #lädt alle Variablen des dictioaries abhängig vom fkt argument am Anfang 
    config[config_name].init_app(app)   #??

    #extensions an app binden, statt nur wie oben zu definieren 
    bootstrap.init_app(app)
    db.init_app(app)
    migrate.init_app(app,db)
    login_manager.init_app(app)

    from . import models

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)   #hängt alle Routen an die App

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix="/auth")

    return app
