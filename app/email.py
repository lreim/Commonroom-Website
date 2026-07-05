import json
from threading import Thread

import urllib.request
from urllib.error import HTTPError, URLError

from flask import current_app, render_template


POSTMARK_API_URL = "https://api.postmarkapp.com/email"


def send_async_email(app, payload):
    with app.app_context():
        token = app.config.get("POSTMARK_API_TOKEN")
        if not token:
            raise RuntimeError("POSTMARK_API_TOKEN is not configured.")

        request = urllib.request.Request(
            POSTMARK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Postmark API error {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Postmark API connection error: {exc}") from exc


def send_email(to, subject, template, message_stream=None, reply_to=None, **kwargs):
    app = current_app._get_current_object()

    payload = {
        "From": app.config.get('TALKTO_MAIL_SENDER'),
        "To": to,
        "Subject": app.config.get('TALKTO_MAIL_SUBJECT_PREFIX', '') + subject,
        "TextBody": render_template(template + '.txt', **kwargs),
        "HtmlBody": render_template(template + '.html', **kwargs),
        "MessageStream": message_stream or "outbound",
    }
    if reply_to:
        payload["ReplyTo"] = reply_to

    thr = Thread(target=send_async_email, args=(app, payload))
    thr.start()
    return thr
