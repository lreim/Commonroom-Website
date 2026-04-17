from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, AnonymousUserMixin
from .auth import login_manager
import hashlib 
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app, request
from datetime import datetime, timezone 


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return '<User %r>' % self.username

    def generate_confirmation_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'confirm': self.id})
    
    def confirm(self, token, max_age=3600):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except Exception:
            return False 
        if data.get('confirm') != self.id:
            return False
        self.confirmed = True
        db.session.commit()
        return True 
    
    #hashing and checking hashed password:  
    @property          #das definiert, was beim Lesen (also bei user.password) passieren soll
    def password(self):
        raise AttributeError('password is not a readable attribute')   #damit man bei user.passwort Fehler bekommt 

    @password.setter    #das macht die methode 'password' zu einem Attribut von User, sodass user.passwort = 'blah' funktioniert
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_email_change_token(self, new_email):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'change_email': self.id, 'new_email': new_email})

    def change_email(self, token, max_age=3600):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except Exception:
            return False
        if data.get('change_email') != self.id:
            return False

        new_email = data.get('new_email')
        if not new_email:
            return False
        if User.query.filter_by(email=new_email).first():
            return False

        self.email = new_email
        db.session.add(self)
        return True

    def ping(self):
        self.last_seen = datetime.now(timezone.utc)
        db.session.add(self)

@login_manager.user_loader      #loads user given the identifier 
def load_user(user_id):
    return User.query.get(int(user_id))
