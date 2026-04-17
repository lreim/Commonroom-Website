import os

basedir = os.path.abspath(os.path.dirname(__file__)) #nötig für path con database 

#configurations used in all cases  
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'  #CSRF Schutz
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    TALKTO_MAIL_SUBJECT_PREFIX = '[TALKTO]'
    TALKTO_MAIL_SENDER = 'TALKTO Developers <lissy.reim@t-online.de>'
    TALKTO_ADMIN = os.environ.get('TALKTO_ADMIN')
    TALKTO_POSTS_PER_PAGE = 20

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