from flask import session
from flask_login import current_user


ADMIN_DEMO_SESSION_KEY = 'admin_demo_mode'


def activate_admin_demo_mode(user):
    if user.is_administrator():
        session[ADMIN_DEMO_SESSION_KEY] = True
    else:
        session.pop(ADMIN_DEMO_SESSION_KEY, None)


def is_admin_demo_mode():
    return (
        current_user.is_authenticated
        and current_user.is_administrator()
        and session.get(ADMIN_DEMO_SESSION_KEY) is True
    )


def set_admin_demo_mode(enabled):
    session[ADMIN_DEMO_SESSION_KEY] = bool(enabled)


def clear_admin_demo_mode():
    session.pop(ADMIN_DEMO_SESSION_KEY, None)
