import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__)) #nötig für path con database 

#configurations used in all cases  
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'  #CSRF Schutz
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    TALKTO_MAIL_SUBJECT_PREFIX = '[COMMONROOM]'
    TALKTO_MAIL_SENDER = 'CommonRoom Developers <lissy.reim@t-online.de>'
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
#app.config['MAIL_SUBJECT_PREFIX'] = '[CommonRoom] '
#app.config['MAIL_SENDER'] = 'CommonRoom Developers <lissy.reim@t-online.de>'
#app.config['TALKTO_ADMIN'] = os.environ.get('TALKTO_ADMIN')







#TODO: ändere Cookie Secure zu True
#      --- done mache form kästchen größer, sodass der graue placeholder text reinpasst --- done 
#      evtl timeout rausmachen und dann nur beim Browserschließen session rememberen oder beenden lassen. 
#      --- done change edit_profile form inputs, think of what is really important and necessary 
#      --- egal/done welche email adressen sollen funktionieren? (Nur die von studenten? oder auch von staff? oder dphys etc? oder muss man auch nur ethz.ch akzeptieren, wenn man student.ethz.ch akzeptiert?)  --- egal/done
#      evtl das mailto für mich als admin rausnehmen, sodass ich nur im Notfall die emails aus der dabenbank lesen kann? ne. 
#      mir als Admin bei jeder neuen Registreierung eine email senden! 
#      --- done evtl einbauen, dass mir schon profile vorgeschlagen werden? 
#      --- done fast done evtl bei dem freien About me text auch schon Vorgaben machen (Current challenge, last challenges, what makes me a good person to help you,... )  --- fast done
#      --- done halb go back auf manchen seiten einbauen (bei login/auth Seiten?) und das unten plazieren links 
#      --- done The Developers contact data unten auf jeder Seite haben? Oder unter About? 
#      --- done wenn ich auf dem profil nach tags suche ode auf der tagseite, dann sollen die matching tags in den existing tags farblich anlaufen? 
#      mache noch etwas mit den missing_tags, die gespeichert werden oder nicht speichern???


#Brainstorming on what to still do:
# - ---done for the chat index of a user, maybe implement a scoring or a filter, to change the scoring of the chats (last messages/most active chat, most recent chat, most overlap of tags?)  ---done
# - implement email notification for new messages and maybe also reminders to stay active? (think about the usecase and atmosphere this app should convey)
# - think of a vibe and style (minimalistic or cozy or what vibe should it give off)
# - ---done move the tags maybe to the right side of the window and not below the matches --- done 
# - maybe change names of users to something more serious
# - ---done halb dark mode color scheme machen ---done halb 
# - ---done bei den forms den grauen Text in die Kästchen reinpassen lassen 
# - ---done ein label vergeben lassen fürs userprofile, das anzeigt, ob jemand sich austauschen will, Fragen/Anliegen hat, oder nur als Helfer da sein will? (voluntary)
# - ---done eine chat anfrage einbauen, die der user an den matching user stellen kann, bevor man chattet, das soll auch per email versendet werden. Und dabei muss ein kurzer Anfragetext geschickt werden 
            # (evtl mit emailvorlage? oder dass man ein Kontaktformular ausfüllt auf der Webseite?)  und dann soll pending unter den chats hinzugefügt werden. Und der User wird aufgefordert (Glocke), die Anfrage nach einer Woche erneut zu senden
# - ---done baue eine Glocke ein mit Benachrichtigungen zu Chats und Anfragen und Updates etc., (oder direkt im Chat Index? ODer im Userprofile?)
# - ---done baue eine Datenschutz seite ein, auf der du erklärt, was du eingebaut hast und warum und wie die Daten geschützt sind. 
# - ---done add a block button for a chat you want to end and block.
# wichtig!!: finde einen Server (evtl an der ETH) zum Hosten und baue dann auf diesem server lokal umami auf und binde es ein. 



# - ---done mehr persönliche Sachen
# - nsch der Anfrage icebreaker frage stellen (send an icebreaker), ich gebe icebreaker vor, ich gebe bei der Anfrage mitgeben (das ist eher, um sich wohler zu fühlen)
# - Liste herausgeben an no-gos, die man nicht sharen sollte, in das about me feld ein screening einbauen bei keywords 
# - reports machen können von den usern 
# - neue message über Telefon sende evtl?
# - andere email für die nachrichten botification nehmen
# - oder nur push nachrichten im Browser 
# - ---done nightline und 321 verlinken 
# - den chat nicht screenen, weil das zu sensible daten sind 


# - antworten können auch posts direkt
# - chat darkmode
# - in notifications direkt auf den chat springen 
# - bei ältere laden im Chat nicht alles dann verschwinden lassen, bis eine neue Nachricht kommt 
# - confirm link resent sehe ich als admin nicht
# - beim kontakt icoon, muss man scjließen können und die email, die geöffnet wird, verschiebt das ganzr Layout der webseite!!!
# - erwähnen, dass man sich keinen namen geben kann in onboardnig 
# - links einbauen in onboardning page, damit man direkt das eigene profil findet und die settings 
# - und die navbar statish lassen, sodass sie nciht vershwidet beim scrollen
# - bei posts ändern, dass klar ist, dass es alle use sein können, die man hier sieht, nicht nur likeminded people., dort aber auch filter einbauen für themen für posts (gleiche tags?)
# - direkt von start a chat auf den user im chat 
# - eine chat request nochmal senen kännen und auch zkommenurückuziehen können
# - timeout evtl anpassen