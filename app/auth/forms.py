from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp, EqualTo 
from wtforms import ValidationError 
from ..models import User 

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Keep me logged in")
    submit = SubmitField("Let's Lock in ;)")

class EmailForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send verification token to reset password")

class ResetForm(FlaskForm):
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(8, 128),
            EqualTo('password2', message='Passwords must match.')
        ]
    )
    password2 = PasswordField("Confirm password", validators=[DataRequired()])
    submit = SubmitField("Save new password")

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Length(8, 64), Email()])
    
    username = StringField('Username(TODO: given)', validators=[DataRequired(), Length(max=64), Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0,
                                                                                        'Usernames must have only letters, '
                                                                                        'numbers, dots or underscores')])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 128),
        Regexp(
            r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d).+$',
            message='Password must contain uppercase, lowercase, and a number.'), 
        EqualTo('password2', message='Passwords must match.')])
    password2 = PasswordField('Confirm password', validators=[DataRequired()])
    submit = SubmitField('Register and join the community! ')

    def validate_email(self, field):
        email = User.normalize_email(field.data)
        if User.query.filter_by(email=email).first():
            raise ValidationError('Email already registered.')
    
    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already in use.')
        

       
class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Old password', validators=[DataRequired()])
    password = PasswordField('New password', validators=[DataRequired(), Length(8, 128), EqualTo('password2', message='Passwords must match.')])
    password2 = PasswordField('Confirm new password', validators=[DataRequired()])
    submit = SubmitField('Update Password')

class ChangeEmailForm(FlaskForm):
    email = StringField('New email', validators=[DataRequired(), Length(8, 64), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Update Email Address')

    def validate_email(self, field):
        email = User.normalize_email(field.data)
        if User.query.filter_by(email=email).first():
            raise ValidationError('Email already registered.')
