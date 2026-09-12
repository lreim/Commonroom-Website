import secrets
import time

from authlib.integrations.base_client.errors import OAuthError
from flask import abort, render_template, redirect, request, url_for, flash, session
from flask import current_app
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy.exc import IntegrityError
from . import auth     #importiert auth object aus __init__.py
from ..models import User
from .forms import LoginForm, OIDCLinkAccountForm, OIDCProfileForm, RegistrationForm, ChangePasswordForm, ChangeEmailForm, ResetForm, EmailForm, canonicalize_eth_email
from .. import db, oauth
from ..email import send_email
from ..security import is_safe_local_redirect_target
from datetime import datetime, timezone, timedelta

LOGIN_ACCOUNT_MAX_FAILURES = 6
LOGIN_ACCOUNT_LOCKOUT_MINUTES = 10
LOGIN_LOCKOUT_WINDOW_HOURS = 24
LOGIN_LOCKOUT_ESCALATION_COUNT = 3
LOGIN_ACCOUNT_SUSPENSION_HOURS = 24
OIDC_PENDING_PROFILE_SESSION_KEY = 'pending_oidc_profile'
OIDC_NEXT_SESSION_KEY = 'oidc_next_url'
OIDC_PENDING_PROFILE_MAX_AGE_SECONDS = 10 * 60
OAUTH_ERROR_CODE_MAX_LENGTH = 64


def _oidc_is_active():
    return current_app.config.get('AUTH_MODE', 'legacy') == 'oidc'


def _oidc_configuration_error():
    required_keys = (
        'OIDC_DISCOVERY_URL',
        'OIDC_CLIENT_ID',
        'OIDC_CLIENT_SECRET',
        'OIDC_REDIRECT_URI',
    )
    missing = [key for key in required_keys if not current_app.config.get(key)]
    if missing:
        return 'SWITCH edu-ID sign-in is not fully configured.'
    return None


def _get_eduid_client():
    return oauth.create_client('eduid')


def _safe_oauth_error_code(exc):
    error_code = getattr(exc, 'error', None)
    if not isinstance(error_code, str) or not error_code:
        return 'unknown_oauth_error'
    allowed_characters = frozenset(
        'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'
    )
    if (
        len(error_code) > OAUTH_ERROR_CODE_MAX_LENGTH
        or any(character not in allowed_characters for character in error_code)
    ):
        return 'unrecognized_oauth_error'
    return error_code


def _claim_values(userinfo, *claim_names):
    values = []
    for claim_name in claim_names:
        value = userinfo.get(claim_name)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(item for item in value if isinstance(item, str))
    return values


def _has_student_affiliation(userinfo):
    affiliations = _claim_values(
        userinfo,
        'eduPersonAffiliation',
        'eduPersonScopedAffiliation',
        'swissEduIDLinkedAffiliation',
    )
    return any(
        value.strip().lower() == 'student'
        or value.strip().lower().startswith('student@')
        for value in affiliations
    )


def _render_oidc_error(message, status_code):
    return render_template('auth/eduid_error.html', message=message), status_code


def _send_security_email(user, subject, template, **kwargs):
    send_email(
        user.email,
        subject,
        template,
        message_stream=current_app.config.get('POSTMARK_MESSAGE_STREAM_SECURITY'),
        user=user,
        **kwargs,
    )


def _reset_login_lockout_window_if_needed(user, now):
    window_started_at = user.login_lockout_window_started_at
    if window_started_at is None or window_started_at + timedelta(hours=LOGIN_LOCKOUT_WINDOW_HOURS) <= now:
        user.login_lockout_window_started_at = now
        user.login_lockout_count = 0


def _register_account_lockout(user, now):
    _reset_login_lockout_window_if_needed(user, now)
    user.login_lockout_count += 1

    if user.login_lockout_count >= LOGIN_LOCKOUT_ESCALATION_COUNT:
        user.account_locked_until = now + timedelta(hours=LOGIN_ACCOUNT_SUSPENSION_HOURS)
        user.login_locked_until = None
        user.failed_login_attempts = 0
        db.session.add(user)
        db.session.commit()
        _send_security_email(
            user,
            'Account temporarily locked',
            'auth/email/account_locked',
            account_locked_until=user.account_locked_until,
            lockout_window_hours=LOGIN_LOCKOUT_WINDOW_HOURS,
        )
        return

    user.login_locked_until = now + timedelta(minutes=LOGIN_ACCOUNT_LOCKOUT_MINUTES)
    db.session.add(user)
    db.session.commit()
    _send_security_email(
        user,
        'Login temporarily locked',
        'auth/email/login_lockout',
        login_locked_until=user.login_locked_until,
        remaining_lockout_count=max(LOGIN_LOCKOUT_ESCALATION_COUNT - user.login_lockout_count, 0),
        lockout_window_hours=LOGIN_LOCKOUT_WINDOW_HOURS,
    )


def _clear_login_failures(user):
    if user is None:
        return
    user.failed_login_attempts = 0
    user.login_locked_until = None
    db.session.add(user)
    db.session.commit()


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if _oidc_is_active():
        return eduid_login()
    return legacy_login()


def legacy_login():
    form = LoginForm()
    if form.validate_on_submit():
        now = datetime.now(timezone.utc)
        next_url = request.args.get('next')
        email = canonicalize_eth_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if user is not None:
            if user.account_locked_until is not None and user.account_locked_until <= now:
                user.account_locked_until = None
                user.login_lockout_count = 0
                user.login_lockout_window_started_at = None
                db.session.add(user)
                db.session.commit()

            if user.account_locked_until is not None and user.account_locked_until > now:
                flash("This account has been temporarily locked. Please check your email for details.")
                return render_template('auth/login.html', form=form)

            if user.login_locked_until is not None and user.login_locked_until <= now:
                user.login_locked_until = None
                user.failed_login_attempts = 0
                db.session.add(user)
                db.session.commit()

            if user.login_locked_until is not None and user.login_locked_until > now:
                flash("Too many failed login attempts. Please try again later.")
                return render_template('auth/login.html', form=form)

            if user.verify_password(form.password.data):
                _clear_login_failures(user)

                login_user(user, form.remember_me.data)
                session.permanent = True
                flash(f"{user.username} is now locked in!")
                return redirect(next_url if is_safe_local_redirect_target(next_url) else url_for('main.index'))

            user.failed_login_attempts += 1
            if user.failed_login_attempts >= LOGIN_ACCOUNT_MAX_FAILURES:
                _register_account_lockout(user, now)
            else:
                db.session.add(user)
                db.session.commit()
        flash('Welp, invalid username or password, my friend.')
    return render_template('auth/login.html', form=form)


@auth.route('/eduid/login')
def eduid_login():
    if not _oidc_is_active():
        abort(404)

    configuration_error = _oidc_configuration_error()
    if configuration_error:
        return _render_oidc_error(configuration_error, 503)

    next_url = request.args.get('next')
    if is_safe_local_redirect_target(next_url):
        session[OIDC_NEXT_SESSION_KEY] = next_url
    else:
        session.pop(OIDC_NEXT_SESSION_KEY, None)
    session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)

    nonce = secrets.token_urlsafe(32)
    try:
        return _get_eduid_client().authorize_redirect(
            redirect_uri=current_app.config['OIDC_REDIRECT_URI'],
            nonce=nonce,
        )
    except Exception as exc:
        current_app.logger.warning(
            'Could not start OIDC authorization (%s).',
            type(exc).__name__,
        )
        return _render_oidc_error(
            'SWITCH edu-ID is temporarily unavailable. Please try again later.',
            503,
        )


@auth.route('/eduid/callback')
def eduid_callback():
    if not _oidc_is_active():
        abort(404)

    configuration_error = _oidc_configuration_error()
    if configuration_error:
        return _render_oidc_error(configuration_error, 503)

    try:
        eduid_client = _get_eduid_client()
        # Authlib consumes and validates the session-bound state here. It also
        # verifies the ID token, including issuer, audience, signature and nonce.
        token = eduid_client.authorize_access_token()
        if not token.get('id_token'):
            raise ValueError('OIDC response did not contain an ID token')
        id_token_claims = dict(token.get('userinfo') or {})
        subject = id_token_claims.get('sub')
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
            raise ValueError('OIDC response did not contain a valid subject')
        subject = subject.strip()
        userinfo = dict(eduid_client.userinfo(token=token))
        if userinfo.get('sub') != subject:
            raise ValueError('UserInfo subject does not match the ID token')
    except (OAuthError, KeyError, TypeError, ValueError) as exc:
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        session.pop(OIDC_NEXT_SESSION_KEY, None)
        if isinstance(exc, OAuthError):
            current_app.logger.warning(
                'OIDC callback validation failed (%s, oauth_error=%s).',
                type(exc).__name__,
                _safe_oauth_error_code(exc),
            )
        else:
            current_app.logger.warning(
                'OIDC callback validation failed (%s).',
                type(exc).__name__,
            )
        return _render_oidc_error(
            'The SWITCH edu-ID response could not be validated. Please start the sign-in again.',
            400,
        )
    except Exception as exc:
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        session.pop(OIDC_NEXT_SESSION_KEY, None)
        current_app.logger.warning(
            'OIDC callback failed (%s).',
            type(exc).__name__,
        )
        return _render_oidc_error(
            'SWITCH edu-ID is temporarily unavailable. Please try again later.',
            503,
        )

    if not _has_student_affiliation(userinfo):
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        session.pop(OIDC_NEXT_SESSION_KEY, None)
        return _render_oidc_error(
            'CommonRoom is currently available only to users with an active student affiliation.',
            403,
        )

    user = User.query.filter_by(oidc_sub=subject).first()
    if user is not None:
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        login_user(user)
        session.permanent = True
        next_url = session.pop(OIDC_NEXT_SESSION_KEY, None)
        flash(f'{user.username} is now locked in!')
        return redirect(next_url if is_safe_local_redirect_target(next_url) else url_for('main.index'))

    session[OIDC_PENDING_PROFILE_SESSION_KEY] = {
        'sub': subject,
        'issued_at': int(time.time()),
    }
    return redirect(url_for('auth.eduid_create_profile'))


def _pending_oidc_subject():
    pending = session.get(OIDC_PENDING_PROFILE_SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    subject = pending.get('sub')
    issued_at = pending.get('issued_at')
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(issued_at, int)
        or time.time() - issued_at > OIDC_PENDING_PROFILE_MAX_AGE_SECONDS
        or issued_at > time.time() + 60
    ):
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        return None
    return subject


@auth.route('/eduid/create-profile', methods=['GET', 'POST'])
def eduid_create_profile():
    if not _oidc_is_active():
        abort(404)

    subject = _pending_oidc_subject()
    if subject is None:
        return _render_oidc_error(
            'Your profile setup session has expired. Please start the SWITCH edu-ID sign-in again.',
            400,
        )

    existing_user = User.query.filter_by(oidc_sub=subject).first()
    if existing_user is not None:
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        login_user(existing_user)
        session.permanent = True
        return redirect(url_for('auth.eduid_welcome'))

    form = OIDCProfileForm()
    if form.validate_on_submit():
        user = User(
            oidc_sub=subject,
            username=User.generate_username(),
            confirmed=True,
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            user = User.query.filter_by(oidc_sub=subject).first()
            if user is None:
                current_app.logger.warning('Could not create OIDC profile (IntegrityError).')
                return _render_oidc_error(
                    'Your anonymous profile could not be created. Please try again.',
                    409,
                )

        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        login_user(user)
        session.permanent = True
        return redirect(url_for('auth.eduid_welcome'))

    return render_template('auth/eduid_profile.html', form=form)


@auth.route('/eduid/link-account', methods=['GET', 'POST'])
def eduid_link_account():
    if not _oidc_is_active():
        abort(404)

    subject = _pending_oidc_subject()
    if subject is None:
        return _render_oidc_error(
            'Your account-linking session has expired. Please start the SWITCH edu-ID sign-in again.',
            400,
        )

    existing_subject_user = User.query.filter_by(oidc_sub=subject).first()
    if existing_subject_user is not None:
        session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
        login_user(existing_subject_user)
        session.permanent = True
        return redirect(url_for('main.index'))

    form = OIDCLinkAccountForm()
    if form.validate_on_submit():
        now = datetime.now(timezone.utc)
        email = canonicalize_eth_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if user is not None:
            if user.account_locked_until is not None and user.account_locked_until <= now:
                user.account_locked_until = None
                user.login_lockout_count = 0
                user.login_lockout_window_started_at = None
                db.session.add(user)
                db.session.commit()

            if user.account_locked_until is not None and user.account_locked_until > now:
                flash('This account has been temporarily locked. Please check your email for details.')
                return render_template('auth/eduid_link_account.html', form=form)

            if user.login_locked_until is not None and user.login_locked_until <= now:
                user.login_locked_until = None
                user.failed_login_attempts = 0
                db.session.add(user)
                db.session.commit()

            if user.login_locked_until is not None and user.login_locked_until > now:
                flash('Too many failed login attempts. Please try again later.')
                return render_template('auth/eduid_link_account.html', form=form)

            if user.verify_password(form.password.data):
                if user.oidc_sub is not None and user.oidc_sub != subject:
                    flash('This CommonRoom profile is already connected to another SWITCH edu-ID.')
                    return render_template('auth/eduid_link_account.html', form=form)

                user.oidc_sub = subject
                user.failed_login_attempts = 0
                user.login_locked_until = None
                db.session.add(user)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    current_app.logger.warning('Could not link OIDC profile (IntegrityError).')
                    return _render_oidc_error(
                        'This SWITCH edu-ID or CommonRoom profile has already been connected.',
                        409,
                    )

                session.pop(OIDC_PENDING_PROFILE_SESSION_KEY, None)
                login_user(user)
                session.permanent = True
                next_url = session.pop(OIDC_NEXT_SESSION_KEY, None)
                flash(f'{user.username} is now connected to SWITCH edu-ID and logged in!')
                return redirect(
                    next_url if is_safe_local_redirect_target(next_url) else url_for('main.index')
                )

            user.failed_login_attempts += 1
            if user.failed_login_attempts >= LOGIN_ACCOUNT_MAX_FAILURES:
                _register_account_lockout(user, now)
            else:
                db.session.add(user)
                db.session.commit()

        flash('The existing CommonRoom email or password is incorrect.')

    return render_template('auth/eduid_link_account.html', form=form)


@auth.route('/eduid/welcome')
@login_required
def eduid_welcome():
    if not _oidc_is_active() or not current_user.oidc_sub:
        abort(404)

    next_url = session.pop(OIDC_NEXT_SESSION_KEY, None)
    continue_url = next_url if is_safe_local_redirect_target(next_url) else url_for('main.post')
    return render_template(
        'auth/eduid_welcome.html',
        continue_url=continue_url,
    )


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
        email = canonicalize_eth_email(form.email.data)
        user = User(
                email=email,
                contact_email=email,
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
