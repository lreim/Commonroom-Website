from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, SelectField, SelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.validators import DataRequired, Length, Email, Regexp
from wtforms import ValidationError
from ..models import User, Role

MAX_POST_BODY_LENGTH = 4000
MAX_PROFILE_ABOUT_ME_LENGTH = 1500
MAX_FUNNY_FACT_LENGTH = 500


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

class PostForm(FlaskForm):
    body = TextAreaField(
        "What's on your mind?",
        validators=[DataRequired(), Length(1, MAX_POST_BODY_LENGTH)],
        render_kw={"maxlength": MAX_POST_BODY_LENGTH},
    )
    submit = SubmitField('Submit')


class FeedbackForm(FlaskForm):
    category = SelectField(
        "What is this about?",
        choices=[
            ("onboarding", "Onboarding"),
            ("profile_tags", "Profile and tags"),
            ("tagsearch", "Tagsearch"),
            ("chat_requests", "Chat requests"),
            ("chat", "Chat"),
            ("posts", "Posts"),
            ("design_usability", "Design / usability"),
            ("bug_report", "Bug report"),
            ("safety_privacy", "Safety / privacy feeling"),
            ("other", "Something else"),
        ],
        validators=[DataRequired()],
    )
    feedback_type = SelectField(
        "How would you describe it?",
        choices=[
            ("confusing", "This confused me"),
            ("annoying", "This was annoying"),
            ("good", "This felt good"),
            ("missing", "This felt missing"),
            ("bug", "This is a bug"),
            ("other", "Other"),
        ],
        validators=[DataRequired()],
    )
    allow_follow_up = BooleanField("You may follow up with me if something is unclear.")
    message = TextAreaField(
        "Your feedback",
        validators=[DataRequired(), Length(10, 3000)],
        render_kw={
            "placeholder": "What happened, what felt unclear, what worked well, what felt missing, or what would you change?"
        },
    )
    submit = SubmitField("Send feedback")


class EditProfileForm(FlaskForm):
    about_me = TextAreaField(
        'About me',
        validators=[Length(0, MAX_PROFILE_ABOUT_ME_LENGTH)],
        render_kw={
            "placeholder": "I study..., issues I struggle with are..., I have gone through... and can tell something about...",
            "maxlength": MAX_PROFILE_ABOUT_ME_LENGTH,
        },
    )
    funny_fact = TextAreaField(
        'Fun fact about me',
        validators=[Length(0, MAX_FUNNY_FACT_LENGTH)],
        render_kw={
            "placeholder": "Tell us a fun fact about yourself or answer one of those:\nWhat is your go-to food?\nWhich study place is the best and why?\nWhich cantine cooks?",
            "maxlength": MAX_FUNNY_FACT_LENGTH,
        },
    )
    tags = StringField('Tags (comma separated)', validators=[Length(0, 256)])
    label = MultiCheckboxField(
            "Profile label",
            choices=User.PROFILE_LABEL_CHOICES,
    )
    submit = SubmitField('Submit')


class EditProfileAdminForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Length(1, 64), Email()])
    username = StringField(
        'Username',
        validators=[
            DataRequired(),
            Length(1, 64),
            Regexp('^[A-Za-z][A-Za-z0-9_.-]*$', 0,
                   'Usernames must have only letters, numbers, hyphens, dots or underscores.')
        ]
    )
    confirmed = BooleanField('Confirmed')
    role = SelectField('Role', coerce=int)
    about_me = TextAreaField('About me', validators=[Length(0, MAX_PROFILE_ABOUT_ME_LENGTH)], render_kw={"maxlength": MAX_PROFILE_ABOUT_ME_LENGTH})
    funny_fact = TextAreaField('Funny fact about me', validators=[Length(0, MAX_FUNNY_FACT_LENGTH)], render_kw={"maxlength": MAX_FUNNY_FACT_LENGTH})
    tags = StringField('Tags (comma separated)', validators=[Length(0, 256)])
    submit = SubmitField('Submit')

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role.choices = [(role.id, role.name) for role in Role.query.order_by(Role.name).all()]
        self.user = user

    def validate_email(self, field):
        if field.data != self.user.email and User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self, field):
        if field.data != self.user.username and User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already in use.')
