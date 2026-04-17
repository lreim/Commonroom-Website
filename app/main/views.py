from app.main import main
from flask import render_template, redirect, request, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from .. import auth     #importiert auth object aus __init__.py


@main.route("/")
def index():
    return render_template('index.html', active_page='index')

@main.route('/about')
def about():
    return render_template('about.html', active_page='about')


@main.route('/rules')
@login_required
def rules():
    return render_template('rules.html', active_page='rules')
