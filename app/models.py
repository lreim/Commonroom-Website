from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, AnonymousUserMixin
from . import db, login_manager
from sqlalchemy.orm import validates
import hashlib, random 
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app, request
from datetime import datetime, timezone 


#role und user Model anlegen als python classes with attributes that match the columns of a corresponding db table
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True) #first argument is column type 
    name = db.Column(db.String(64), unique=True) #second arg: no duplicates allowed 
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)       #permissions field, which is an integer that will be used as bit flags. Each task will be assigned a bit position, and for each role the tasks that are allowed for that role will have their bits set to 1.
    users = db.relationship('User', backref='role', lazy='dynamic') #1.:model on the other relationship side, 3.:to stay a query

    def __repr__(self):                          # method for readable string representation (debugging)
        return '<Role %r>' % self.name
    
    @staticmethod
    def insert_roles():
        roles = {
            'User': (Permission.FOLLOW |
                    Permission.COMMENT |
                    Permission.WRITE_ARTICLES, True),   #default = True 
            'Moderator': (Permission.FOLLOW |
                         Permission.COMMENT |
                         Permission.WRITE_ARTICLES |
                         Permission.MODERATE_COMMENTS, False),
            'Administrator': (0xff, False)
        }
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.permissions = roles[r][0]
            role.default = roles[r][1]
            db.session.add(role)
        db.session.commit()


user_tags = db.Table(
    'user_tags',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
)

    
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id')) #column is interpreted as having id calues from rows in role table
    confirmed = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)
    last_seen = db.Column(db.DateTime(), default=datetime.utcnow)
    tags = db.relationship('Tag', secondary=user_tags, back_populates='users', lazy='subquery')
    
    def __repr__(self):
        return '<User %r>' % self.username

    @staticmethod
    def generate_username():
        adjectives = ["quiet", "lucid", "steady", "subtle", "bright", "calm", "gentle", "keen", "vivid", "patient", 
                      "hidden", "rapid", "silver", "amber", "curious", "clever", "atomic", "cosmic", "linear", "radial"]

        science_nouns = ["vector", "tensor", "matrix", "scalar", "theorem", "lemma", "integral", "gradient", "eigen", "prime", "fractal", "vertex", "axis", "quark", "photon", "neutrino",
                         "proton", "boson", "fermion", "plasma", "ion", "lattice", "pulse", "flux", "quasar", "nova", "comet", "nebula", "eclipse", "aurora", "isotope",
                         "molecule", "atom", "genome", "catalyst", "crystal", "signal", "orbit", "spectrum", "cosmos"]

        while True:
            username = f"{random.choice(adjectives)}-{random.choice(science_nouns)}-{random.randint(1000, 9999)}"
            if not User.query.filter_by(username=username).first():
                return username
            
    @staticmethod
    def normalize_email(email):
        return email.strip().lower() if email else email

    @validates('email')
    def _normalize_email(self, key, email):
        return self.normalize_email(email)

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
        new_email = self.normalize_email(new_email)
        if User.query.filter_by(email=new_email).first():
            return False

        self.email = new_email
        db.session.add(self)
        return True
    
    def generate_reset_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'reset': self.id})

    @staticmethod
    def reset_password(token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=3600)
        except Exception:
            return False
        user = User.query.get(data.get('reset'))
        if user is None:
            return False
        user.password = new_password
        db.session.add(user)
        db.session.commit()
        return True

    
    #when registering initialise user with a specific email (TALKTO_ADMIN) with administrator role 
    def __init__(self, **kwargs):
        if 'email' in kwargs:
            kwargs['email'] = self.normalize_email(kwargs['email'])
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email == current_app.config['TALKTO_ADMIN']:
                self.role = Role.query.filter_by(permissions=0xff).first()
            if self.role is None:   #falls ADMIN ROlle nicht gefunden, wird default gesetzt 
                self.role = Role.query.filter_by(default=True).first()
    
    def can(self, permissions):
        return self.role is not None and \
            (self.role.permissions & permissions) == permissions
    
    def is_administrator(self):
        return self.can(Permission.ADMINISTER)

    def ping(self):
        self.last_seen = datetime.now(timezone.utc)
        db.session.add(self)

    def set_tags_from_string(self, raw_tags, allow_create=False):
        names = []
        seen = set()
        for chunk in (raw_tags or '').split(','):
            name = chunk.strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)

        tags = []
        missing = []
        for name in names:
            tag = Tag.query.filter_by(name=name).first()
            if tag is None:
                if allow_create:
                    tag = Tag(name=name)
                    db.session.add(tag)
                else:
                    missing.append(name)
                    continue
            tags.append(tag)
        self.tags = tags
        return missing

    @property
    def tag_string(self):
        return ', '.join(sorted(tag.name for tag in self.tags))

    # Keep the existing call sites, but serve DiceBear thumbs avatars instead.
    def gravatar(self, size=100, default='robohash', rating='g'):
        seed = str(self.id) if self.id is not None else (self.username or self.email or 'anonymous')
        return f'https://api.dicebear.com/9.x/thumbs/svg?seed={seed}&size={size}'
    
    #generate fake users  (nur für development)
    @staticmethod
    def generate_fake(count=100):
        from sqlalchemy.exc import IntegrityError
        from random import seed, randint, sample, choice
        import forgery_py

        tag_pool = [
            'uni life', 'campus life', 'exam stress', 'exam anxiety', 'finals pressure',
            'study strategy', 'study planning', 'focus', 'concentration', 'procrastination',
            'mental load', 'overthinking', 'self doubt', 'motivation', 'burnout',
            'stress management', 'sleep issues', 'loneliness', 'homesickness',
            'friendship', 'making friends', 'social anxiety', 'belonging',
            'time management', 'work life balance', 'financial stress', 'relationship stress',
            'career uncertainty', 'imposter syndrome', 'panic feelings',
            'emotional support', 'coping skills'
        ]
        intro_pool = [
            'Trying to navigate university life and stay mentally balanced.',
            'Looking for honest conversations about study pressure and personal growth.',
            'I like exchanging practical strategies for exams and focus.',
            'Interested in supportive communities and meaningful friendships on campus.',
            'Sharing real experiences about stress, doubt, and motivation.',
            'Building better habits for learning, structure, and wellbeing.'
        ]
        challenge_pool = [
            'Current challenge: managing exam anxiety and staying consistent with study plans.',
            'Current challenge: balancing social life, deadlines, and sleep.',
            'Current challenge: reducing procrastination and keeping focus during long sessions.',
            'Current challenge: handling self-doubt and pressure before assessments.',
            'Current challenge: finding belonging and better peer connections at university.',
            'Current challenge: coping with overwhelm while trying to stay motivated.'
        ]

        seed()
        for i in range(count):
            chosen_tags = sample(tag_pool, randint(4, 7))
            about_line = f"{choice(intro_pool)} {choice(challenge_pool)} Interests: {', '.join(chosen_tags)}."
            u = User(email=forgery_py.internet.email_address(),
                    username=forgery_py.internet.user_name(True),
                    password=forgery_py.lorem_ipsum.word(),
                    confirmed=True,
                    name=forgery_py.name.full_name(),
                    location=forgery_py.address.city(),
                    about_me=about_line,
                    member_since=forgery_py.date.date(True))
            db.session.add(u)
            u.set_tags_from_string(', '.join(chosen_tags), allow_create=True)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()

    
@login_manager.user_loader      #loads user given the identifier 
def load_user(user_id):
    return User.query.get(int(user_id))

class Permission:
    FOLLOW = 0x01
    COMMENT = 0x02
    WRITE_ARTICLES = 0x04
    MODERATE_COMMENTS = 0x08
    ADMINISTER = 0x80

class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False
    
    def is_administrator(self):
        return False


login_manager.anonymous_user = AnonymousUser


#new model for blog posts
class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.now(timezone.utc))
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    @staticmethod
    def generate_fake(count=100):
        from random import seed, randint
        from datetime import datetime, timezone
        import forgery_py

        seed()
        user_count = User.query.count()
        if user_count == 0:
            return

        for _ in range(count):
            u = User.query.offset(randint(0, user_count - 1)).first()
            p = Post(
                body=forgery_py.lorem_ipsum.sentences(randint(1, 3)),
                timestamp=datetime.now(timezone.utc),
                author=u
            )
            db.session.add(p)
        db.session.commit()

class Conversation(db.Model):
    __tablename__ = "conversations"
    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user_b_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user_a = db.relationship("User", foreign_keys=[user_a_id])
    user_b = db.relationship("User", foreign_keys=[user_b_id])
    messages = db.relationship("Message", backref="conversation", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
    )   #das sit der constraint, dass es nur einen Chat pro unique Paar gibt

    #Zugriffsprüfung für Nutzer, ob er zum Chat gehört. 
    def has_user(self, user_id):
        return user_id in (self.user_a_id, self.user_b_id)  #prüft, ob user_id in a oder b ist doer nicht 

    def other_user(self, user_id):
        return self.user_b if self.user_a_id == user_id else self.user_a


class Message(db.Model):    #einzelne Nachricht 
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    author = db.relationship("User")


class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, index=True, nullable=False)
    users = db.relationship('User', secondary=user_tags, back_populates='tags', lazy='dynamic')

    def __repr__(self):
        return f'<Tag {self.name}>'

    @staticmethod
    def seed_defaults():
        tag_pool = [
            'uni life', 'campus life', 'exam stress', 'exam anxiety', 'finals pressure',
            'study strategy', 'study planning', 'focus', 'concentration', 'procrastination',
            'mental load', 'overthinking', 'self doubt', 'motivation', 'burnout', 'imposter syndrome',
            'stress management', 'sleep issues', 'loneliness', 'homesickness',
            'friendship', 'making friends', 'social anxiety', 'belonging',
            'time management', 'work life balance', 'financial stress', 'relationship stress',
            'career uncertainty', 'panic feelings', 'household', 'finding internships',
            'emotional support', 'coping skills'
        ]

        for name in tag_pool:
            normalized_name = name.strip().lower()
            if not Tag.query.filter_by(name=normalized_name).first():
                db.session.add(Tag(name=normalized_name))
        db.session.commit()
