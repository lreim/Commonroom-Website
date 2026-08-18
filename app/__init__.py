from datetime import datetime, timezone
from flask import Flask, render_template
from flask_bootstrap import Bootstrap
from flask_mail import Mail
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect

#erst nur definieren, damit nicht direkt die App importiert werden muss (gut für Tests)
bootstrap = Bootstrap()
mail = Mail()
moment = Moment()
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins='*')
csrf = CSRFProtect()

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
    mail.init_app(app)
    moment.init_app(app)
    db.init_app(app)
    migrate.init_app(app,db)
    login_manager.init_app(app)
    socketio.init_app(app)
    csrf.init_app(app)
    

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)   #hängt alle Routen an die App

    from .auth import auth as auth_blueprint 
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .chat import chat as chat_blueprint 
    app.register_blueprint(chat_blueprint, url_prefix='/chat')

    from .chat import events 

    @app.context_processor
    def inject_session_timeout():
        notification_payload = {"items": [], "has_unseen": False}
        if current_user.is_authenticated:
            from .notifications import build_notifications_for_user

            notification_payload = build_notifications_for_user(current_user)
        lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
        timeout_minutes = int(lifetime.total_seconds() // 60) if lifetime else 0
        return dict(
            session_timeout_minutes=timeout_minutes,
            current_time=datetime.now(timezone.utc),
            notification_items=notification_payload["items"],
            has_unseen_notifications=notification_payload["has_unseen"],
        )
    
    # attach routes and custom error pages here
    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Tag
        return dict(db=db, User=User, Tag=Tag)

    return app
