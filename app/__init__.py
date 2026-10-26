from datetime import datetime, timezone
from flask import Flask, render_template, redirect, request, url_for, session
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
from authlib.integrations.flask_client import OAuth

#erst nur definieren, damit nicht direkt die App importiert werden muss (gut für Tests)
bootstrap = Bootstrap()
mail = Mail()
moment = Moment()
db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()
oauth = OAuth()

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

    @login_manager.unauthorized_handler
    def handle_unauthorized_access():
        return_path = request.full_path if request.query_string else request.path
        return redirect(url_for('auth.login', next=return_path, gate=1))
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get('TALKTO_SITE_ORIGIN'),
    )
    csrf.init_app(app)
    oauth.init_app(app)
    oauth.register(
        name='eduid',
        client_id=app.config.get('OIDC_CLIENT_ID'),
        client_secret=app.config.get('OIDC_CLIENT_SECRET'),
        server_metadata_url=app.config.get('OIDC_DISCOVERY_URL'),
        client_kwargs={
            'scope': 'openid https://eduid.ch/scope/userinfo.read',
            'token_endpoint_auth_method': 'client_secret_basic',
        },
    )
    

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)   #hängt alle Routen an die App

    from .auth import auth as auth_blueprint 
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .chat import chat as chat_blueprint 
    app.register_blueprint(chat_blueprint, url_prefix='/chat')

    from .reports import reports as reports_blueprint
    app.register_blueprint(reports_blueprint)

    from .chat import events 

    @app.context_processor
    def inject_session_timeout():
        from .admin_demo import is_admin_demo_mode
        from .models import VisitPurposeSurveyEvent
        from datetime import timedelta

        notification_payload = {"items": [], "has_unseen": False}
        if current_user.is_authenticated:
            from .notifications import build_notifications_for_user

            notification_payload = build_notifications_for_user(current_user)
        lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
        timeout_minutes = int(lifetime.total_seconds() // 60) if lifetime else 0
        admin_demo_mode = is_admin_demo_mode()

        visit_purpose_survey = None
        survey_endpoints = {'main.analytics', 'main.admin_sunday_checkins', 'auth.login', 'auth.register'}
        if request.endpoint not in survey_endpoints and not (request.endpoint or '').startswith('static'):
            now = datetime.now(timezone.utc)
            survey_user_id = current_user.id if current_user.is_authenticated else None
            if survey_user_id:
                member_since = current_user.member_since
                if member_since and member_since.tzinfo is None:
                    member_since = member_since.replace(tzinfo=timezone.utc)
                latest = (VisitPurposeSurveyEvent.query.filter_by(user_id=survey_user_id)
                          .order_by(VisitPurposeSurveyEvent.created_at.desc()).first())
                # The onboarding question is shown only once, on the first
                # authenticated visit after registration. Afterwards every
                # three-day cycle uses the current-visit question.
                audience = ('new' if not latest and member_since and
                            member_since >= now - timedelta(days=3) else 'existing')
            else:
                # Keep the anonymous survey identity in a persistent browser
                # session so reloads cannot create a fresh visitor token.
                session.permanent = True
                visitor_token = session.get('visit_purpose_survey_token')
                if not visitor_token:
                    import secrets
                    visitor_token = secrets.token_urlsafe(24)
                    session['visit_purpose_survey_token'] = visitor_token
                audience = 'visitor'
                latest = (VisitPurposeSurveyEvent.query.filter_by(visitor_token=visitor_token)
                          .order_by(VisitPurposeSurveyEvent.created_at.desc()).first())
            latest_at = latest.created_at if latest else None
            if latest_at and latest_at.tzinfo is None:
                latest_at = latest_at.replace(tzinfo=timezone.utc)
            followup = session.get('visit_purpose_survey_followup') == 'needs'
            snoozed_until = session.get('visit_purpose_survey_snoozed_until')
            if snoozed_until:
                try:
                    snoozed_until = datetime.fromisoformat(snoozed_until)
                    if snoozed_until.tzinfo is None:
                        snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
                except ValueError:
                    snoozed_until = None
            if followup:
                audience = 'new_followup'
            # The admin has a one-day schedule offset via the login preview,
            # but the recurring interval remains three days for everyone.
            cooldown_days = 3
            existing_initial_delay = (audience == 'existing' and latest_at is None and
                                      now < (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)))
            if (followup or not snoozed_until or snoozed_until <= now) and (followup or
                (not existing_initial_delay and (not latest_at or latest_at <= now - timedelta(days=cooldown_days)))):
                cycle_started = session.get('visit_purpose_survey_cycle_started_at')
                if cycle_started:
                    try:
                        cycle_started = datetime.fromisoformat(cycle_started)
                        if cycle_started.tzinfo is None:
                            cycle_started = cycle_started.replace(tzinfo=timezone.utc)
                    except ValueError:
                        cycle_started = None
                if cycle_started and cycle_started <= now - timedelta(days=3) and not followup:
                    session['visit_purpose_survey_cycle_index'] = session.get('visit_purpose_survey_cycle_index', 0) + 1
                    cycle_started = None
                if not cycle_started and not followup:
                    session['visit_purpose_survey_cycle_started_at'] = now.isoformat()
                    session.modified = True
                recurring_questions = [
                    'What brings you to CommonRoom today?',
                    'What would help you most right now?',
                    'What are you hoping to find here today?',
                    'What made you come back to CommonRoom?',
                ]
                recurring_choices = [
                    [('read', 'Read what others shared'), ('share', 'Share something'), ('reply', 'Reply or connect'), ('checkin', 'Take a check-in'), ('chat', 'Use private chat'), ('other', 'Something else')],
                    [('advice', 'Advice or a practical tip'), ('listening', 'Someone to listen'), ('reassurance', 'Reassurance'), ('resources', 'Useful resources'), ('connection', 'A real connection'), ('unsure', "I’m not sure yet")],
                    [('understanding', 'Understand something better'), ('feel_less_alone', 'Feel less alone'), ('new_perspective', 'Find a new perspective'), ('be_heard', 'Feel heard'), ('quiet_space', 'A quiet space to think'), ('curious', 'Just curious')],
                    [('new_post', 'A new post or conversation'), ('checkin', 'The weekly check-in'), ('reply', 'A reply or notification'), ('chat', 'A private chat'), ('routine', 'My usual routine'), ('other', 'Something else')],
                ]
                recurring_index = session.get('visit_purpose_survey_cycle_index', 0) % len(recurring_questions)
                recurring_question = recurring_questions[recurring_index]
                visit_purpose_survey = {
                    'audience': audience,
                    'question': ('What would be most useful for you here right now?' if audience == 'new_followup' else
                                 'What first brought you to CommonRoom?' if audience == 'new' else
                                 recurring_question if audience == 'existing' else
                                 'What brought you to CommonRoom today?'),
                    'choices': ([('advice', 'Advice or a practical tip'), ('share', 'A place to share without judgment'),
                                 ('private_chat', 'Someone to talk to privately'), ('information', 'Information or support'),
                                 ('reading', 'Just reading around'), ('unsure', "I'm not sure yet")] if audience == 'new_followup' else
                                [('curiosity', 'I was curious'), ('support', 'I wanted support'),
                                 ('recommendation', 'Someone recommended it'), ('event', 'I came from an event or link'),
                                 ('other', 'Something else')] if audience == 'new' else
                                recurring_choices[recurring_index] if audience == 'existing' else
                                [('read', 'Read what others shared'), ('post', 'Share something'),
                                 ('reply', 'Reply or connect'), ('checkin', 'Take a check-in'),
                                 ('chat', 'Use private chat'), ('other', 'Something else')]),
                }

        def display_username(user):
            if admin_demo_mode and user.id == current_user.id:
                return 'Admin'
            return user.username

        def display_avatar_url(user, size=40):
            if admin_demo_mode and user.id == current_user.id:
                return url_for('static', filename='Logo_Website_small.jpg')
            return user.gravatar(size=size)

        return dict(
            session_timeout_minutes=timeout_minutes,
            current_time=datetime.now(timezone.utc),
            notification_items=notification_payload["items"],
            has_unseen_notifications=notification_payload["has_unseen"],
            admin_demo_mode=admin_demo_mode,
            display_username=display_username,
            display_avatar_url=display_avatar_url,
            visit_purpose_survey=visit_purpose_survey,
        )
    
    # attach routes and custom error pages here
    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Tag
        return dict(db=db, User=User, Tag=Tag)

    return app
