from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from . import db
from .decorators import admin_required
from .email import send_email
from .models import ContentReport, Message, Post

reports = Blueprint('reports', __name__)


def _send_report_email(report):
    path = url_for('reports.detail', report_id=report.id)
    origin = (current_app.config.get('TALKTO_SITE_ORIGIN') or request.url_root).rstrip('/')
    try:
        send_email(
            current_app.config['TALKTO_REPORT_EMAIL'],
            f'Report #{report.id}: {report.target_type} #{report.target_id}',
            'reports/email',
            message_stream=current_app.config['POSTMARK_MESSAGE_STREAM_REPORT'],
            synchronous=True,
            report=report,
            report_url=origin + path,
        )
    except Exception:
        # The report is already committed; failed notifications remain visible to admins.
        current_app.logger.exception('Email delivery failed for report %s', report.id)
        return False
    report.email_sent_at = datetime.now(timezone.utc)
    db.session.commit()
    return True


@reports.route('/reports/<target_type>/<int:target_id>', methods=['POST'])
@login_required
def create(target_type, target_id):
    if target_type == 'post':
        target = Post.query.get_or_404(target_id)
    elif target_type == 'message':
        target = Message.query.get_or_404(target_id)
        if not target.conversation.has_user(current_user.id) or target.author_id == current_user.id:
            abort(403)
    else:
        abort(404)

    existing = ContentReport.query.filter_by(
        reporter_id=current_user.id, target_type=target_type, target_id=target_id,
    ).first()
    if existing:
        return jsonify(message='You have already reported this message.')

    report = ContentReport(
        target_type=target_type, target_id=target_id,
        reporter_id=current_user.id, reporter_username=current_user.username,
        author_id=target.author_id,
        author_username=target.author.username if target.author else 'CommonRoom Admin',
        body=target.body or '',
    )
    db.session.add(report)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if ContentReport.query.filter_by(reporter_id=current_user.id, target_type=target_type, target_id=target_id).first():
            return jsonify(message='You have already reported this message.')
        raise
    _send_report_email(report)
    return jsonify(message='Your report has been submitted. Thank you.'), 201


@reports.route('/admin/reports')
@login_required
@admin_required
def index():
    page = request.args.get('page', 1, type=int)
    pagination = ContentReport.query.order_by(ContentReport.created_at.desc(), ContentReport.id.desc()).paginate(
        page=page, per_page=30, error_out=False,
    )
    counts = dict(db.session.query(ContentReport.target_type, func.count(ContentReport.id)).group_by(ContentReport.target_type).all())
    target_counts = db.session.query(
        ContentReport.target_type, ContentReport.target_id, func.count(ContentReport.id).label('report_count'),
        func.max(ContentReport.id).label('latest_report_id'),
    ).group_by(ContentReport.target_type, ContentReport.target_id).subquery()
    totals = db.session.query(ContentReport, target_counts.c.report_count).join(
        target_counts, ContentReport.id == target_counts.c.latest_report_id,
    ).order_by(target_counts.c.report_count.desc(), ContentReport.id.desc()).paginate(
        page=request.args.get('targets_page', 1, type=int), per_page=30, error_out=False,
    )
    return render_template('reports/index.html', pagination=pagination, totals=totals, counts=counts,
                           pending_count=ContentReport.query.filter_by(email_sent_at=None).count())


@reports.route('/admin/reports/<int:report_id>')
@login_required
@admin_required
def detail(report_id):
    report = ContentReport.query.get_or_404(report_id)
    model = Post if report.target_type == 'post' else Message
    target = db.session.get(model, report.target_id)
    original_url = None
    if target is not None and report.target_type == 'post':
        root = target
        while root.parent is not None:
            root = root.parent
        original_url = url_for('main.post_thread', post_id=root.id, _anchor=f'post-{target.id}')
    count = ContentReport.query.filter_by(target_type=report.target_type, target_id=report.target_id).count()
    return render_template('reports/detail.html', report=report, target=target, original_url=original_url, count=count)


@reports.route('/admin/reports/<int:report_id>/resend', methods=['POST'])
@login_required
@admin_required
def resend(report_id):
    report = ContentReport.query.get_or_404(report_id)
    if report.email_sent_at is None:
        sent = _send_report_email(report)
        flash('Report email sent.' if sent else 'Email could not be sent. The report is saved; please try again later.')
    return redirect(url_for('reports.detail', report_id=report.id))
