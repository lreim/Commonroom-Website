from flask import render_template, redirect, request, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from . import auth     #importiert auth object aus __init__.py
#from ..models import User 
from .forms import LoginForm, RegistrationForm #ChangePasswordForm, ChangeEmailForm
#from .. import db 
#from ..email import send_email

@auth.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        flash(f"{form.email.data} locked in!")
        return redirect(url_for("main.index"))
    return render_template("auth/login.html", form=form)

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
        #user = User(email=form.email.data, username=form.username.data, password=form.password.data)
       # db.session.add(user)
        #db.session.commit()
        #token = user.generate_confirmation_token()
        #send_email(user.email, 'Please Confirm Your Account', 'auth/email/confirm', user=user, token=token)
        flash('A confirmation email has been sent to you. Pls take a look!')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
