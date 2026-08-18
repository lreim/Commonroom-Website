from flask import render_template, redirect, request, url_for, flash, session 
from flask import current_app
from flask_login import login_user, login_required, logout_user, current_user
from . import auth     #importiert auth object aus __init__.py
from ..models import User
from .forms import LoginForm, RegistrationForm, ChangePasswordForm, ChangeEmailForm, ResetForm, EmailForm, canonicalize_eth_email
from .. import db 
from ..email import send_email
from datetime import datetime, timezone, timedelta



@auth.route('/login', methods=['GET', 'POST'])
def login():   
    form = LoginForm()
    if form.validate_on_submit():
        email = canonicalize_eth_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if user is not None:
            now = datetime.now(timezone.utc)

            if user.login_locked_until is not None and user.login_locked_until <= now:
                user.login_locked_until = None
                user.failed_login_attempts = 0

            if user.login_locked_until is not None and user.login_locked_until > now:
                flash("Too many failed login attempts. Please try again later.")
                return render_template('index.html')

            if user.verify_password(form.password.data):
                user.failed_login_attempts = 0
                user.login_locked_until = None
                db.session.commit()

                login_user(user, form.remember_me.data)
                session.permanent = True
                flash(f"{user.username} is now locked in!")
                return redirect(request.args.get('next') or url_for('main.index'))

            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 6:
                user.login_locked_until = now + timedelta(minutes=10)
            db.session.commit()
        flash('Welp, invalid username or password, my friend.')
    return render_template('auth/login.html', form=form)


@auth.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()     #removes and resets the user session
    flash('You have been logged out, see you soon!')
    return redirect(url_for('main.index'))


@auth.route('/reset_password_mail', methods=['GET', 'POST'])
def reset_password_mail():
    if not current_user.is_anonymous:
        return redirect(url_for('main.index'))
    form = form = EmailForm()
    if form.validate_on_submit():
        email = canonicalize_eth_email(form.email.data)
        user = User.query.filter_by(email=email).first()
        if user is not None:
            token = user.generate_reset_token()
            send_email(
                user.email,
                'Reset Your Password',
                'auth/email/reset_password',
                message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_PASSWORD_RESET'),
                user=user,
                token=token
            )
        flash('If that email exists in our system, a reset link has been sent.')     #always the same flash message so that one cant find out which emails are registered 
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password_mail.html', form=form)


@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if not current_user.is_anonymous:
        return redirect(url_for('main.index'))

    form = ResetForm()
    if form.validate_on_submit():
        user = User.reset_password(token, form.password.data)
        if user:
            flash('Your password has been updated.')
            return redirect(url_for('auth.login'))
        flash('The reset link is invalid or has expired.')
        return redirect(url_for('auth.reset_password_unconfirmed'))
    return render_template('auth/reset_password.html', form=form)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
                email=canonicalize_eth_email(form.email.data),
                username=User.generate_username(),
                password=form.password.data
                )

        db.session.add(user)
        db.session.commit()
        token = user.generate_confirmation_token()
        send_email(
            user.email,
            'Please Confirm Your Account',
            'auth/email/confirm',
            message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_REGISTRATION'),
            user=user,
            token=token
        )
        admin_email = current_app.config.get('TALKTO_ADMIN')
        if admin_email:
            send_email(
                admin_email,
                'New user registration',
                'auth/email/new_registration',
                message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_ADMIN_REGISTRATION'),
                user=user,
            )
        flash('A confirmation email has been sent to you. Pls take a look!')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth.route('/confirm/<token>')
@login_required    #first log in after clicking on link in email
def confirm(token):
    if current_user.confirmed:     #checks if already confirmed 
        return redirect(url_for('main.index'))
    if current_user.confirm(token):   #just calls confirm method which is defined in User model and returns True/False
        flash('You have successfully confiremd your account. Thanks and Welcome to the community!')
    else:
        flash('The confirmation link is invalid or has expired, sorry.')
        redirect(url_for('auth/unconfirmed.html'))
    return redirect(url_for('main.index'))

@auth.before_app_request   #wichtig! läft vor jedem app request 
def before_request():
    if current_user.is_authenticated:
        current_user.ping()
        if not current_user.confirmed \
                and request.endpoint \
                and request.endpoint[:5] != 'auth.':    #request is outside of auth blueprint
            return redirect(url_for('auth.unconfirmed'))
    
@auth.route('/unconfirmed')
def unconfirmed():     #prüft, ob der user schon confirmed hat, sonst unconfirmed Seite rendern 
    if current_user.is_anonymous or current_user.confirmed:
        return redirect(url_for('main.index'))
    return render_template('auth/unconfirmed.html')

@auth.route('/confirm', methods=['POST'])
@login_required
def resend_confirmation():
    token = current_user.generate_confirmation_token()
    send_email(
        current_user.email,
        'Confirm Your Account',
        'auth/email/confirm',
        message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_RESEND_CONFIRMATION'),
        user=current_user,
        token=token
    )
    flash('A new confirmation email has been sent to you by email.')
    return redirect(url_for('main.index'))

@auth.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.verify_password(form.old_password.data):
            current_user.password = form.password.data
            db.session.commit()
            flash('Your password has been updated.')
            return redirect(url_for('main.settings'))
        flash('Invalid old password.')
    return render_template('auth/change_password.html', form=form)

@auth.route('/change_email', methods=['GET', 'POST'])
@login_required
def change_email_request():
    form = ChangeEmailForm()
    if form.validate_on_submit():
        if current_user.verify_password(form.password.data):
            token = current_user.generate_email_change_token(canonicalize_eth_email(form.email.data))
            send_email(
                canonicalize_eth_email(form.email.data),
                'Confirm your email address',
                'auth/email/change_email',
                message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_CHANGE_EMAIL'),
                user=current_user,
                token=token
            )
            flash('A confirmation email has been sent to your new address.')
            return redirect(url_for('main.settings'))
        flash('Invalid password.')
    return render_template('auth/change_email_request.html', form=form)

@auth.route('/change_email/<token>')
@login_required
def change_email(token):
    if current_user.change_email(token):
        db.session.commit()
        flash('Your email address has been updated.')
    else:
        flash('Invalid or expired link.')
        redirect(url_for('auth/change_email_request.html'))
    return redirect(url_for('main.settings'))
