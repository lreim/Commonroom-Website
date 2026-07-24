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


class UserBlock(db.Model):
    __tablename__ = "user_blocks"
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_pair"),
    )

    blocker = db.relationship("User", foreign_keys=[blocker_id], back_populates="blocks_initiated")
    blocked = db.relationship("User", foreign_keys=[blocked_id], back_populates="blocks_received")

    
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    PROFILE_LABEL_CHOICES = [
        ("listener", "Open to share experience"),
        ("peer_support", "Need advice urgently"),
        ("practical_advice", "Happy to talk"),
        ("all", "Allrounder"),
    ]
    PROFILE_LABEL_MAP = dict(PROFILE_LABEL_CHOICES)

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id')) #column is interpreted as having id calues from rows in role table
    confirmed = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    name = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    funny_fact = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)
    last_seen = db.Column(db.DateTime(), default=datetime.utcnow)
    tags = db.relationship('Tag', secondary=user_tags, back_populates='users', lazy='subquery')
    blocks_initiated = db.relationship(
        "UserBlock",
        foreign_keys="UserBlock.blocker_id",
        back_populates="blocker",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    blocks_received = db.relationship(
        "UserBlock",
        foreign_keys="UserBlock.blocked_id",
        back_populates="blocked",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    chat_requests_sent = db.relationship(
        "ChatRequest",
        foreign_keys="ChatRequest.requester_id",
        back_populates="requester",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    chat_requests_received = db.relationship(
        "ChatRequest",
        foreign_keys="ChatRequest.requested_id",
        back_populates="requested",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    failed_login_attempts = 0
    login_locked_until = None
    profile_label = db.Column(db.String(32))  
    
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

    @staticmethod
    def canonicalize_eth_email(email):
        email = User.normalize_email(email)
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        if domain in {"ethz.ch", "student.ethz.ch"}:
            return f"{local}@ethz.ch"
        return email

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
        new_email = self.canonicalize_eth_email(new_email)
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

    def has_blocked(self, other_user):
        if other_user is None:
            return False
        other_id = other_user.id if isinstance(other_user, User) else int(other_user)
        return self.blocks_initiated.filter_by(blocked_id=other_id).first() is not None

    def is_blocked_by(self, other_user):
        if other_user is None:
            return False
        other_id = other_user.id if isinstance(other_user, User) else int(other_user)
        return self.blocks_received.filter_by(blocker_id=other_id).first() is not None

    def has_block_relationship(self, other_user):
        return self.has_blocked(other_user) or self.is_blocked_by(other_user)

    def set_profile_labels(self, labels):
        selected = []
        seen = set()
        valid_values = set(self.PROFILE_LABEL_MAP.keys())
        for label in labels or []:
            if not label or label not in valid_values or label in seen:
                continue
            seen.add(label)
            selected.append(label)
        self.profile_label = ",".join(selected)

    @property
    def profile_label_values(self):
        if not self.profile_label:
            return []
        values = []
        seen = set()
        valid_values = set(self.PROFILE_LABEL_MAP.keys())
        for chunk in self.profile_label.split(","):
            value = chunk.strip()
            if not value or value not in valid_values or value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values

    @property
    def profile_label_texts(self):
        return [self.PROFILE_LABEL_MAP[value] for value in self.profile_label_values]

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
    parent_id = db.Column(db.Integer, db.ForeignKey('posts.id'), index=True)

    parent = db.relationship(
        'Post',
        remote_side=[id],
        backref=db.backref('replies', lazy='dynamic', cascade='all, delete-orphan')
    )

    @property
    def is_reply(self):
        return self.parent_id is not None

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


class ChatRequest(db.Model):
    __tablename__ = "chat_requests"
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    requested_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    responded_at = db.Column(db.DateTime, nullable=True)

    requester = db.relationship("User", foreign_keys=[requester_id], back_populates="chat_requests_sent")
    requested = db.relationship("User", foreign_keys=[requested_id], back_populates="chat_requests_received")

    def other_user(self, user_id):
        return self.requested if self.requester_id == user_id else self.requester

    def direction_for(self, user_id):
        return "outgoing" if self.requester_id == user_id else "incoming"

    def generate_response_token(self, action):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps(
            {
                'chat_request': self.id,
                'requested_id': self.requested_id,
                'action': action,
            }
        )

    @staticmethod
    def resolve_response_token(token, expected_action=None, max_age=604800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except Exception:
            return None

        request_id = data.get('chat_request')
        requested_id = data.get('requested_id')
        action = data.get('action')

        if expected_action is not None and action != expected_action:
            return None

        chat_request = ChatRequest.query.get(request_id)
        if chat_request is None:
            return None
        if chat_request.requested_id != requested_id:
            return None
        return chat_request


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
            # Academic pressure and study process
            'exam stress', 'exam anxiety', 'finals pressure', 'study strategy',
            'study planning', 'focus', 'concentration', 'procrastination', 'time management',
            'thesis stress', 'master thesis pressure', 'phd pressure', 'lab stress',
            'group projects', 'deadline pressure', 'presentation anxiety',
            'oral exam anxiety', 'academic pressure', 'finding internships',
            'feeling behind', 'fear of failure', 'career uncertainty',

            # Mental and emotional struggles
            'mental load', 'overthinking', 'self doubt', 'motivation', 'burnout',
            'study burnout', 'imposter syndrome', 'panic feelings', 'stress management',
            'coping skills', 'perfectionism', 'decision fatigue', 'sleep issues',
            'low energy', 'restlessness', 'morning anxiety', 'depressive thoughts',
            'anxiety spirals', 'grief', 'self worth', 'guilt', 'shame',
            'emotional numbness', 'constant comparison', 'fear of the future',
            'fear of disappointing others', 'difficulty asking for help',

            # Social and belonging-related struggles
            'loneliness', 'homesickness', 'social anxiety', 'belonging',
            'emotional support', 'isolation', 'family pressure',

            # Daily life and environment
            'work life balance', 'financial stress', 'lack of structure',
            'messy routine', 'conflict with flatmates', 'household',
            'digital overload', 'phone addiction', 'body image', 'seasonal blues'
        ]

        for name in tag_pool:
            normalized_name = name.strip().lower()
            if not Tag.query.filter_by(name=normalized_name).first():
                db.session.add(Tag(name=normalized_name))
        db.session.commit()


class PageVisit(db.Model):
    __tablename__ = "page_visits"

    id = db.Column(db.Integer, primary_key=True)
    page_key = db.Column(db.String(64), nullable=False, index=True)
    path = db.Column(db.String(255), nullable=False)
    visit_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    ended_at = db.Column(db.DateTime, nullable=False, index=True)
    duration_seconds = db.Column(db.Integer, nullable=False, default=0)

    user = db.relationship("User")
