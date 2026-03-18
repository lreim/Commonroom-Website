from app.main import main
from flask import render_template


@main.route("/")
def index():
    return render_template('index.html', active_page='index')

@main.route('/about')
def about():
    return render_template('about.html', active_page='about')


@main.route('/rules')
#@login_required
def rules():
    return render_template('rules.html', active_page='rules')
