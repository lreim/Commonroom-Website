from flask import render_template, redirect, request, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from . import auth     #importiert auth object aus __init__.py
from ..models import User 
from .forms import LoginForm, RegistrationForm, ChangePasswordForm, ChangeEmailForm
from .. import db 
from ..email import send_email


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            flash(f"{form.email.data} locked in!")
            return redirect(request.args.get('next') or url_for('main.index'))
        flash('Welp, invalid username or password, my friend.')
    return render_template('auth/login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()     #removes and resets the user session
    flash('You have been logged out, see you soon!')
    return redirect(url_for('main.index'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data, username=form.username.data, password=form.password.data)
        db.session.add(user)
        db.session.commit()
        token = user.generate_confirmation_token()
        send_email(user.email, 'Please Confirm Your Account', 'auth/email/confirm', user=user, token=token)
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
                and request.endpoint[:5] != 'auth.':    #rewuest is outside of auth blueprint
            return redirect(url_for('auth.unconfirmed'))
    
@auth.route('/unconfirmed')
def unconfirmed():     #prüft, ob der user schon confirmed hat, sonst unconfirmed Seite rendern 
    if current_user.is_anonymous or current_user.confirmed:
        return redirect(url_for('main.index'))
    return render_template('auth/unconfirmed.html')

@auth.route('/confirm')
@login_required
def resend_confirmation():
    token = current_user.generate_confirmation_token()
    send_email(current_user.email,
                'Confirm Your Account', 'auth/email/confirm', user = current_user, token=token)
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
            return redirect(url_for('main.index'))
        flash('Invalid old password.')
    return render_template('auth/change_password.html', form=form)

@auth.route('/change_email', methods=['GET', 'POST'])
@login_required
def change_email_request():
    form = ChangeEmailForm()
    if form.validate_on_submit():
        if current_user.verify_password(form.password.data):
            token = current_user.generate_email_change_token(form.email.data)
            send_email(
                form.email.data,
                'Confirm your email address',
                'auth/email/change_email',
                user=current_user,
                token=token
            )
            flash('A confirmation email has been sent to your new address.')
            return redirect(url_for('main.index'))
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
    return redirect(url_for('main.index'))
