from flask import flash, redirect, render_template, url_for
from app.auth import auth
from app.auth.forms import LoginForm

@auth.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        flash(f"Login submitted for {form.email.data}")
        return redirect(url_for("main.index"))
    return render_template("auth/login.html", form=form)
