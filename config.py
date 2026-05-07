import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__)) #nötig für path con database 

#configurations used in all cases  
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'  #CSRF Schutz
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    TALKTO_MAIL_SUBJECT_PREFIX = '[TALKTO]'
    TALKTO_MAIL_SENDER = 'TALKTO Developers <lissy.reim@t-online.de>'
    TALKTO_ADMIN = os.environ.get('TALKTO_ADMIN')
    TALKTO_POSTS_PER_PAGE = 20
    #für Sicherheit bei Nutzung von Login session cookies 
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=20)   #damit man automatisch ausgeloggt werden kann nach einer bestimmten Zeitspanne, 
                                                     # der cookie überträgt login daten von request zu request
    REMEMBER_COOKIE_DURATION = timedelta(days=7)        # cookie, der den user wiedererkennt, wenn remember_me aktiviert wurde, damit man sich nicht einloggen muss.
    REMEMBER_COOKIE_HTTPONLY = False #True für Deploy!!!!!# !!!!!!!!!!!!!!!!!!!!!!
    REMEMBER_COOKIE_SECURE = False
    REMEMBER_COOKIE_SAMESITE = "Lax"

    @staticmethod
    def init_app(app):
        pass

#for using flash mail via t-online 
class DevelopmentConfig(Config):
    DEBUG = True    #debug Hilfe 
    MAIL_SERVER = 'securesmtp.t-online.de'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False    #evtl egal 
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data-dev.sqlite')
 #different databases for development, tests and later

class TestingConfig(Config):
    TESTING = True 
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data-test.sqlite')

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, 'data.sqlite')

#dictionary for switching cases, these are the classes from above 
config = {
'development': DevelopmentConfig,
'testing': TestingConfig,
'production': ProductionConfig,
'default': DevelopmentConfig
}

#wenn ich im Terminal export MAIL_PASSWORD="blah" mache und dann app.py importiere, dann liest diese Zeile mein eingegebenes Passwort
#layout for automated e-Mail:
#app.config['MAIL_SUBJECT_PREFIX'] = '[TalkTo] '
#app.config['MAIL_SENDER'] = 'TalkTo Developers <lissy.reim@t-online.de>'
#app.config['TALKTO_ADMIN'] = os.environ.get('TALKTO_ADMIN')







#TODO: ändere Cookie Secure zu True
#      mache form kästchen größer, sodass der graue placeholder text reinpasst 
#      evtl timeout rausmachen und dann nur beim Browserschließen session rememberen oder beenden lassen. 
#      change edit_profile form inputs, think of what is really important and necessary 
#      welche email adressen sollen funktionieren? (Nur die von studenten? oder auch von staff? oder dphys etc? oder muss man auch nur ethz.ch akzeptieren, wenn man student.ethz.ch akzeptiert?)
#      evtl das mailto für mich als admin rausnehmen, sodass ich nur im Notfall die emails aus der dabenbank lesen kann? 
#      mir als Admin bei jeder neuen Registreierung eine email senden! 
#      umami tracking einbauen? 
#      evtl einbauen, dass mir schon profile vorgeschlagen werden? 
#      evtl bei dem freien About me text auch schon Vorgaben machen (Current challenge, last challenges, what makes me a good person to help you,... )
#      go back auf manchen seiten einbauen (bei login/auth Seiten?) und das unten plazieren links 
#      The Developers contact data unten auf jeder Seite haben? Oder unter About? 