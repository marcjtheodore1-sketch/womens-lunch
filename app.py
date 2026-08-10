"""London Autism Group Charity activities registration service.

The application hosts the Autistic Women's Lunch and Autistic Film Club in a
single PythonAnywhere/Flask deployment.
"""

from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for,
    flash, Response, abort
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, time, timezone
from functools import wraps
from email.message import EmailMessage
from html import escape
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
import csv
import calendar
import io
import secrets
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///lunch_bookings.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration. Credentials must be configured in the PythonAnywhere
# environment and are deliberately never stored in source control.
app.config['SMTP_HOST'] = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', '587'))
app.config['SMTP_USER'] = os.environ.get('SMTP_USER', '')
app.config['SMTP_PASSWORD'] = os.environ.get('SMTP_PASSWORD', '')
app.config['SMTP_FROM'] = os.environ.get('SMTP_FROM', app.config['SMTP_USER'])
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', 'wg.lagc@gmail.com')
app.config['ENABLE_EMAIL'] = os.environ.get('ENABLE_EMAIL', 'false').lower() == 'true'

# Admin password
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'change-me-in-pythonanywhere')
app.config['WORKPLACE_ADMIN_PASSWORD'] = os.environ.get(
    'WORKPLACE_ADMIN_PASSWORD', 'change-me-in-pythonanywhere'
)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', 'false').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

db = SQLAlchemy(app)

# ============================================================================
# DATABASE MODELS
# ============================================================================

class LunchDate(db.Model):
    """Available lunch dates"""
    id = db.Column(db.Integer, primary_key=True)
    lunch_date = db.Column(db.Date, nullable=False, unique=True)
    is_bookable = db.Column(db.Boolean, default=True)
    max_attendees = db.Column(db.Integer, default=12)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Booking(db.Model):
    """Lunch bookings"""
    id = db.Column(db.Integer, primary_key=True)
    lunch_date_id = db.Column(db.Integer, db.ForeignKey('lunch_date.id'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    
    # Menu selection
    main_course = db.Column(db.String(200), nullable=False)
    drink = db.Column(db.String(200), nullable=False)
    dietary_requirements = db.Column(db.Text, nullable=True)
    
    # Meeting preference
    meeting_preference = db.Column(db.String(50), nullable=True)
    
    # Additional info
    is_first_time = db.Column(db.Boolean, default=True)
    additional_info = db.Column(db.Text, nullable=True)
    
    # Booking tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancel_token = db.Column(db.String(64), unique=True)
    
    lunch_date_ref = db.relationship('LunchDate', backref='bookings')

class Setting(db.Model):
    """Configurable settings"""
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)


class FilmSession(db.Model):
    """A monthly Film Club screening."""
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False, unique=True)
    arrival_time = db.Column(db.Time, nullable=False, default=time(17, 0))
    film_start_time = db.Column(db.Time, nullable=False, default=time(17, 30))
    end_time = db.Column(db.Time, nullable=False, default=time(20, 0))
    film_title = db.Column(db.String(240), nullable=True)
    film_details = db.Column(db.Text, nullable=True)
    max_attendees = db.Column(db.Integer, nullable=False, default=15)
    is_bookable = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FilmBooking(db.Model):
    """An adult attendee's place at a Film Club screening."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(254), nullable=False, index=True)
    is_adult = db.Column(db.Boolean, nullable=False, default=False)
    access_needs = db.Column(db.Text, nullable=True)
    seating_preferences = db.Column(db.Text, nullable=True)
    comfort_information = db.Column(db.Text, nullable=True)
    dietary_requirements = db.Column(db.Text, nullable=True)
    interested_in_nominating = db.Column(db.Boolean, nullable=False, default=False)
    future_updates_opt_in = db.Column(db.Boolean, nullable=False, default=False)
    cancel_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    session_ref = db.relationship('FilmSession', backref='film_bookings')


class FilmNomination(db.Model):
    """A film suggested by a community member."""
    id = db.Column(db.Integer, primary_key=True)
    nominator_name = db.Column(db.String(200), nullable=False)
    nominator_email = db.Column(db.String(254), nullable=False, index=True)
    film_title = db.Column(db.String(240), nullable=False)
    why_this_film = db.Column(db.Text, nullable=False)
    introduction_notes = db.Column(db.Text, nullable=True)
    can_introduce = db.Column(db.Boolean, nullable=False, default=True)
    availability_notes = db.Column(db.Text, nullable=True)
    content_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default='new')
    selected_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    selected_session = db.relationship('FilmSession', backref='selected_nominations')


class FilmVolunteer(db.Model):
    """One volunteer rota assignment for a Film Club session."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False)
    volunteer_name = db.Column(db.String(200), nullable=False)
    volunteer_email = db.Column(db.String(254), nullable=True)
    role = db.Column(db.String(120), nullable=False, default='Session volunteer')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    session_ref = db.relationship('FilmSession', backref='volunteer_assignments')


class FilmContact(db.Model):
    """A past or current attendee who may receive future invitations."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    source = db.Column(db.String(120), nullable=False, default='Film Club booking')
    can_invite = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_invited_at = db.Column(db.DateTime, nullable=True)


class FilmBookingSupport(db.Model):
    """Companion, carer and responsibility information for a Film Club booking."""
    id = db.Column(db.Integer, primary_key=True)
    film_booking_id = db.Column(db.Integer, db.ForeignKey('film_booking.id'), nullable=False, unique=True)
    attendee_phone = db.Column(db.String(40), nullable=False)
    attending_with_others = db.Column(db.Boolean, nullable=False, default=False)
    additional_attendee_count = db.Column(db.Integer, nullable=False, default=0)
    companion_details = db.Column(db.Text, nullable=True)
    has_carer_or_support_worker = db.Column(db.Boolean, nullable=False, default=False)
    carer_name = db.Column(db.String(200), nullable=True)
    carer_organisation = db.Column(db.String(240), nullable=True)
    carer_mobile = db.Column(db.String(40), nullable=True)
    responsibility_details = db.Column(db.Text, nullable=True)
    support_boundary_acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    booking_ref = db.relationship(
        'FilmBooking', backref=db.backref('support_details', uselist=False, cascade='all, delete-orphan')
    )


class FilmInvitationRun(db.Model):
    """The single permitted past-attendee invitation run for one session."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False, unique=True)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    session_ref = db.relationship(
        'FilmSession', backref=db.backref('invitation_run', uselist=False, cascade='all, delete-orphan')
    )


class FilmTitleNotification(db.Model):
    """Records title-announcement emails so the same announcement is not repeated."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False)
    film_title = db.Column(db.String(240), nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recipient_count = db.Column(db.Integer, nullable=False, default=0)
    session_ref = db.relationship('FilmSession', backref='title_notifications')
    __table_args__ = (
        db.UniqueConstraint('film_session_id', 'film_title', name='uq_film_title_notification'),
    )


class FilmTitleRecipient(db.Model):
    """Tracks each successful title email, allowing failed addresses to be retried safely."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False)
    film_title = db.Column(db.String(240), nullable=False)
    recipient_email = db.Column(db.String(254), nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint(
            'film_session_id', 'film_title', 'recipient_email',
            name='uq_film_title_recipient',
        ),
    )


class FilmSessionMessage(db.Model):
    """Optional extra confirmation-email message for one Film Club session."""
    id = db.Column(db.Integer, primary_key=True)
    film_session_id = db.Column(db.Integer, db.ForeignKey('film_session.id'), nullable=False, unique=True)
    confirmation_note = db.Column(db.Text, nullable=False, default='')
    session_ref = db.relationship(
        'FilmSession', backref=db.backref('email_message', uselist=False, cascade='all, delete-orphan')
    )


class FilmSetting(db.Model):
    """Film Club-only configurable text settings."""
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)


class FilmNewsItem(db.Model):
    """One optional rotating news item on the Film Club homepage."""
    id = db.Column(db.Integer, primary_key=True)
    emoji = db.Column(db.String(20), nullable=True)
    headline = db.Column(db.String(240), nullable=False)
    details = db.Column(db.Text, nullable=True)
    link_url = db.Column(db.String(1000), nullable=True)
    link_text = db.Column(db.String(160), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkplaceSession(db.Model):
    """A monthly Autistic Workplace Support Session."""
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False, unique=True)
    start_time = db.Column(db.Time, nullable=False, default=time(13, 0))
    end_time = db.Column(db.Time, nullable=False, default=time(16, 0))
    max_attendees = db.Column(db.Integer, nullable=False, default=15)
    is_bookable = db.Column(db.Boolean, nullable=False, default=True)
    public_notes = db.Column(db.Text, nullable=True)
    confirmation_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkplaceBooking(db.Model):
    """A registration for one Autistic Workplace Support Session."""
    id = db.Column(db.Integer, primary_key=True)
    workplace_session_id = db.Column(db.Integer, db.ForeignKey('workplace_session.id'), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(254), nullable=False, index=True)
    phone = db.Column(db.String(40), nullable=False)
    is_adult = db.Column(db.Boolean, nullable=False, default=False)
    attend_mentoring = db.Column(db.Boolean, nullable=False, default=False)
    attend_group_discussion = db.Column(db.Boolean, nullable=False, default=False)
    attended_before = db.Column(db.Boolean, nullable=True)
    support_hoped_for = db.Column(db.Text, nullable=True)
    access_needs = db.Column(db.Text, nullable=True)
    dietary_requirements = db.Column(db.Text, nullable=True)
    additional_information = db.Column(db.Text, nullable=True)
    attending_with_others = db.Column(db.Boolean, nullable=False, default=False)
    additional_attendee_count = db.Column(db.Integer, nullable=False, default=0)
    companion_details = db.Column(db.Text, nullable=True)
    has_carer_or_support_worker = db.Column(db.Boolean, nullable=False, default=False)
    carer_name = db.Column(db.String(200), nullable=True)
    carer_organisation = db.Column(db.String(240), nullable=True)
    carer_mobile = db.Column(db.String(40), nullable=True)
    responsibility_details = db.Column(db.Text, nullable=True)
    support_boundary_acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    future_updates_opt_in = db.Column(db.Boolean, nullable=False, default=False)
    cancel_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    session_ref = db.relationship('WorkplaceSession', backref='workplace_bookings')


class WorkplaceVolunteer(db.Model):
    """One volunteer rota assignment for a Workplace Support session."""
    id = db.Column(db.Integer, primary_key=True)
    workplace_session_id = db.Column(db.Integer, db.ForeignKey('workplace_session.id'), nullable=False)
    volunteer_name = db.Column(db.String(200), nullable=False)
    volunteer_email = db.Column(db.String(254), nullable=True)
    role = db.Column(db.String(120), nullable=False, default='Volunteer')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    session_ref = db.relationship('WorkplaceSession', backref='volunteer_assignments')


class WorkplaceSetting(db.Model):
    """Workplace Support-only configurable email settings."""
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)


class WorkplaceContact(db.Model):
    """A past AWSS attendee who may receive manual future invitations."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    source = db.Column(db.String(120), nullable=False, default='AWSS attendee import')
    can_invite = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_invited_at = db.Column(db.DateTime, nullable=True)


class WorkplaceInvitationRun(db.Model):
    """The single permitted past-attendee invitation run for one AWSS date."""
    id = db.Column(db.Integer, primary_key=True)
    workplace_session_id = db.Column(
        db.Integer, db.ForeignKey('workplace_session.id'), nullable=False, unique=True
    )
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    session_ref = db.relationship(
        'WorkplaceSession',
        backref=db.backref('invitation_run', uselist=False, cascade='all, delete-orphan'),
    )


class WorkplaceNewsItem(db.Model):
    """One optional rotating news item on the AWSS homepage."""
    id = db.Column(db.Integer, primary_key=True)
    emoji = db.Column(db.String(20), nullable=True)
    headline = db.Column(db.String(240), nullable=False)
    details = db.Column(db.Text, nullable=True)
    link_url = db.Column(db.String(1000), nullable=True)
    link_text = db.Column(db.String(160), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================================================
# LUNCH DATES CONFIGURATION
# ============================================================================

# Pre-configured lunch dates for 2026
# Format: YYYY-MM-DD
LUNCH_DATES = [
    '2026-04-11',  # April lunch
    '2026-05-09',  # May lunch
    '2026-06-13',  # June lunch
    '2026-07-11',  # July lunch
    '2026-08-08',  # August lunch
    '2026-09-12',  # September lunch
    '2026-10-10',  # October lunch
    '2026-11-21',  # November lunch
    '2026-12-05',  # December lunch
]

FILM_SESSION_DATES = [
    '2026-09-16',
    '2026-10-21',
    '2026-11-18',
    '2026-12-16',
    '2027-01-20',
    '2027-02-17',
]

FILM_VENUE_NAME = 'Artizan Street Library'
FILM_VENUE_ADDRESS = '1 Artizan Street, London E1 7AF'
FILM_MAP_URL = 'https://www.google.com/maps/search/?api=1&query=Artizan+Street+Library%2C+1+Artizan+Street%2C+London+E1+7AF'
LONDON_TZ = ZoneInfo('Europe/London')
DEFAULT_FILM_CONFIRMATION_MESSAGE = (
    'Your place is confirmed. We look forward to welcoming you to a relaxed, '
    'autistic-neuroaffirming Film Club session.'
)
WORKPLACE_VENUE_NAME = 'King Square Community Centre'
WORKPLACE_VENUE_ADDRESS = 'Blackwell House, Pankhurst Terrace, King Square, London EC1Y 8DY'
WORKPLACE_MAP_URL = 'https://maps.app.goo.gl/VqY8KUgkeEUmnrEH6'
DEFAULT_WORKPLACE_CONFIRMATION_MESSAGE = (
    'Your free place is confirmed. We look forward to welcoming you to an '
    'autistic-led, low-demand Workplace Support Session.'
)
COMMUNITY_GUIDELINES_URL = 'https://www.londonautismgroupcharity.org/community-guidelines'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_setting(key, default=None):
    """Get a setting value"""
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def set_setting(key, value):
    """Set a setting value"""
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    db.session.commit()

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def workplace_admin_required(f):
    """Decorator for the separately authenticated Workplace Support admin area."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('workplace_admin_logged_in'):
            return redirect(url_for('admin_login', next=url_for('workplace_admin')))
        return f(*args, **kwargs)
    return decorated_function


def csrf_token():
    """Return a per-session CSRF token for HTML forms and admin API calls."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = csrf_token


def valid_csrf():
    supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token', '')
    expected = session.get('_csrf_token', '')
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


def require_csrf():
    if not valid_csrf():
        abort(400, description='The form expired. Please refresh the page and try again.')


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    return response


def clean_text(value, max_length=None):
    cleaned = (value or '').strip()
    return cleaned[:max_length] if max_length else cleaned


def valid_email(value):
    value = clean_text(value, 254).lower()
    return value if '@' in value and '.' in value.rsplit('@', 1)[-1] else None


def booking_party_size(booking):
    support = booking.support_details
    return 1 + (support.additional_attendee_count if support else 0)


app.jinja_env.globals['booking_party_size'] = booking_party_size


def workplace_party_size(booking):
    return 1 + booking.additional_attendee_count


app.jinja_env.globals['workplace_party_size'] = workplace_party_size


def workplace_booking_time_label(booking):
    if booking.attend_mentoring and not booking.attend_group_discussion:
        return '1pm–2:30pm'
    if booking.attend_group_discussion and not booking.attend_mentoring:
        return '2:45pm–4pm'
    return '1pm–4pm'


app.jinja_env.globals['workplace_booking_time_label'] = workplace_booking_time_label


def workplace_session_summary(workplace_session):
    active = WorkplaceBooking.query.filter_by(
        workplace_session_id=workplace_session.id, cancelled_at=None
    ).all()
    attendee_count = sum(workplace_party_size(item) for item in active)
    return {
        'session': workplace_session,
        'booking_count': len(active),
        'attendee_count': attendee_count,
        'places_left': max(0, workplace_session.max_attendees - attendee_count),
        'is_full': attendee_count >= workplace_session.max_attendees,
    }


def get_workplace_setting(key, default=''):
    setting = WorkplaceSetting.query.filter_by(key=key).first()
    return setting.value if setting else default


def set_workplace_setting(key, value):
    setting = WorkplaceSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.session.add(WorkplaceSetting(key=key, value=value))


def upsert_workplace_contact(name, email, can_invite, source='AWSS attendee import'):
    contact = WorkplaceContact.query.filter_by(email=email).first()
    if contact:
        if name and not contact.name:
            contact.name = name
        contact.can_invite = contact.can_invite or can_invite
    else:
        contact = WorkplaceContact(
            name=name, email=email, can_invite=can_invite, source=source
        )
        db.session.add(contact)
    return contact


def next_last_saturdays(start_date=None, count=6):
    """Return the next `count` last Saturdays, including the current month when future."""
    cursor = (start_date or datetime.now().date()).replace(day=1)
    dates = []
    while len(dates) < count:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        candidate = cursor.replace(day=last_day)
        candidate -= timedelta(days=(candidate.weekday() - calendar.SATURDAY) % 7)
        if candidate >= (start_date or datetime.now().date()):
            dates.append(candidate)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return dates


def film_session_summary(film_session):
    active_bookings = FilmBooking.query.filter_by(
        film_session_id=film_session.id, cancelled_at=None
    ).all()
    active_count = len(active_bookings)
    attendee_count = sum(booking_party_size(item) for item in active_bookings)
    return {
        'session': film_session,
        'booking_count': active_count,
        'attendee_count': attendee_count,
        'places_left': max(0, film_session.max_attendees - attendee_count),
        'is_full': attendee_count >= film_session.max_attendees,
    }


def get_film_setting(key, default=''):
    setting = FilmSetting.query.filter_by(key=key).first()
    return setting.value if setting else default


def set_film_setting(key, value):
    setting = FilmSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.session.add(FilmSetting(key=key, value=value))


def film_confirmation_subject(film_session):
    template = get_film_setting(
        'registration_confirmation_subject',
        'Film Club booking confirmed - {date}',
    )
    return template.replace(
        '{date}', film_session.session_date.strftime('%d %B %Y')
    ).replace(
        '{film}', film_session.film_title or 'Film to be announced'
    )[:240]


def html_paragraphs(value):
    """Escape administrator-authored plain text and preserve line breaks."""
    return escape(value or '').replace('\n', '<br>')


def community_guidelines_email_html():
    return f"""<div style="background:#f5f0ff;border:2px solid #8a68c3;padding:14px;border-radius:8px;margin:18px 0">
    <strong>Community guidelines</strong>
    <p style="margin:6px 0">Please ensure you and everyone attending with you follow our
    <a href="{COMMUNITY_GUIDELINES_URL}"><strong>charity community guidelines</strong></a>.
    They apply across all LAGC in-person initiatives and help keep the space safe and comfortable for everyone.</p>
    <p style="margin:6px 0 0"><strong>If the guidelines are not followed, we may need to suspend someone’s participation</strong>
    in this and other LAGC in-person initiatives. We would always talk to you first wherever we can.</p></div>"""


def film_session_datetimes(film_session):
    start_local = datetime.combine(
        film_session.session_date, film_session.arrival_time, tzinfo=LONDON_TZ
    )
    end_local = datetime.combine(
        film_session.session_date, film_session.end_time, tzinfo=LONDON_TZ
    )
    return start_local, end_local


def google_calendar_url(film_session):
    start_local, end_local = film_session_datetimes(film_session)
    start_utc = start_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    end_utc = end_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    title = 'LAGC Autistic Film Club'
    if film_session.film_title:
        title += f': {film_session.film_title}'
    details = (
        'Arrive from 5pm. The film begins at approximately 5:30–5:45pm, '
        'followed by a friendly volunteer-facilitated discussion. The session ends at 8pm.'
    )
    params = {
        'action': 'TEMPLATE', 'text': title,
        'dates': f'{start_utc}/{end_utc}', 'details': details,
        'location': f'{FILM_VENUE_NAME}, {FILM_VENUE_ADDRESS}',
    }
    return 'https://calendar.google.com/calendar/render?' + '&'.join(
        f'{key}={quote_plus(value)}' for key, value in params.items()
    )


def film_calendar_ics(film_session, booking=None):
    start_local, end_local = film_session_datetimes(film_session)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    start_utc = start_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    end_utc = end_local.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    title = 'LAGC Autistic Film Club'
    if film_session.film_title:
        title += f': {film_session.film_title}'
    uid_suffix = booking.cancel_token if booking else str(film_session.id)

    def ics_escape(value):
        return str(value).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

    description = (
        'Arrive from 5pm. Film starts around 5:30–5:45pm. '
        'A volunteer-facilitated discussion follows and the session ends at 8pm.'
    )
    return '\r\n'.join([
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//London Autism Group Charity//Autistic Film Club//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
        f'UID:film-club-{uid_suffix}@londonautismgroupcharity.org', f'DTSTAMP:{stamp}',
        f'DTSTART:{start_utc}', f'DTEND:{end_utc}', f'SUMMARY:{ics_escape(title)}',
        f'DESCRIPTION:{ics_escape(description)}',
        f'LOCATION:{ics_escape(FILM_VENUE_NAME + ", " + FILM_VENUE_ADDRESS)}',
        'END:VEVENT', 'END:VCALENDAR', ''
    ])


def workplace_session_datetimes(workplace_session):
    return (
        datetime.combine(
            workplace_session.session_date, workplace_session.start_time, tzinfo=LONDON_TZ
        ),
        datetime.combine(
            workplace_session.session_date, workplace_session.end_time, tzinfo=LONDON_TZ
        ),
    )


def workplace_google_calendar_url(workplace_session, booking=None):
    start_local, end_local = workplace_session_datetimes(workplace_session)
    if booking and booking.attend_mentoring and not booking.attend_group_discussion:
        end_local = datetime.combine(
            workplace_session.session_date, time(14, 30), tzinfo=LONDON_TZ
        )
    elif booking and booking.attend_group_discussion and not booking.attend_mentoring:
        start_local = datetime.combine(
            workplace_session.session_date, time(14, 45), tzinfo=LONDON_TZ
        )
    selected_details = (
        'One-to-one autistic employment mentoring.'
        if booking and booking.attend_mentoring and not booking.attend_group_discussion
        else 'A supportive and confidential Speaking Circle about work and related experiences.'
        if booking and booking.attend_group_discussion and not booking.attend_mentoring
        else 'One-to-one mentoring from 1pm to 2:30pm, followed by a confidential Speaking Circle from 2:45pm to 4pm.'
    )
    params = {
        'action': 'TEMPLATE',
        'text': 'LAGC Autistic Workplace Support Session',
        'dates': (
            f'{start_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}/'
            f'{end_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
        ),
        'details': f'Free autistic-led workplace support. {selected_details}',
        'location': f'{WORKPLACE_VENUE_NAME}, {WORKPLACE_VENUE_ADDRESS}',
    }
    return 'https://calendar.google.com/calendar/render?' + '&'.join(
        f'{key}={quote_plus(value)}' for key, value in params.items()
    )


def workplace_calendar_ics(workplace_session, booking=None):
    start_local, end_local = workplace_session_datetimes(workplace_session)
    if booking and booking.attend_mentoring and not booking.attend_group_discussion:
        end_local = datetime.combine(
            workplace_session.session_date, time(14, 30), tzinfo=LONDON_TZ
        )
    elif booking and booking.attend_group_discussion and not booking.attend_mentoring:
        start_local = datetime.combine(
            workplace_session.session_date, time(14, 45), tzinfo=LONDON_TZ
        )
    uid_suffix = booking.cancel_token if booking else str(workplace_session.id)

    def ics_escape(value):
        return str(value).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

    return '\r\n'.join([
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        'PRODID:-//London Autism Group Charity//Autistic Workplace Support//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
        f'UID:workplace-support-{uid_suffix}@londonautismgroupcharity.org',
        f'DTSTAMP:{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',
        f'DTSTART:{start_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',
        f'DTEND:{end_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}',
        'SUMMARY:LAGC Autistic Workplace Support Session',
        f'DESCRIPTION:{ics_escape("Your selected Workplace Support session time is " + (workplace_booking_time_label(booking) if booking else "1pm–4pm") + ".")}',
        f'LOCATION:{ics_escape(WORKPLACE_VENUE_NAME + ", " + WORKPLACE_VENUE_ADDRESS)}',
        'END:VEVENT', 'END:VCALENDAR', '',
    ])


def workplace_confirmation_email(booking, cancel_url, calendar_url):
    workplace_session = booking.session_ref
    opening = html_paragraphs(get_workplace_setting(
        'registration_confirmation_message', DEFAULT_WORKPLACE_CONFIRMATION_MESSAGE
    ))
    selected_parts = []
    if booking.attend_mentoring:
        selected_parts.append('1pm–2:30pm one-to-one mentoring')
    if booking.attend_group_discussion:
        selected_parts.append('2:45pm–4pm Speaking Circle')
    session_note = ''
    if workplace_session.confirmation_note:
        session_note = (
            '<div style="background:#fff7d6;border:2px solid #e0b54b;padding:14px;'
            'border-radius:8px;margin:18px 0"><strong>Important information for this session</strong><br>'
            f'{html_paragraphs(workplace_session.confirmation_note)}</div>'
        )
    party_note = ''
    if booking.attending_with_others:
        party_note = (
            f'<p><strong>Your booking covers:</strong> you and {booking.additional_attendee_count} '
            f'additional attendee{"s" if booking.additional_attendee_count != 1 else ""}.</p>'
        )
    return f"""<!doctype html><html><body style="font-family:Inter,Arial,sans-serif;color:#172033;line-height:1.6;max-width:640px;margin:auto;padding:24px">
    <div style="background:#fff0f2;border-left:5px solid #c82e48;padding:18px;border-radius:10px">
      <h1 style="font-size:22px;margin:0 0 8px;color:#98233b">Your Workplace Support place is confirmed</h1>
      <p style="margin:0">Hello {escape(booking.full_name)}. {opening}</p>
    </div>
    <h2 style="font-size:18px;color:#98233b">Session details</h2>
    <p><strong>Date:</strong> {workplace_session.session_date.strftime('%A %d %B %Y')}<br>
    <strong>Time:</strong> {workplace_booking_time_label(booking)}<br>
    <strong>You selected:</strong> {escape('; '.join(selected_parts))}<br>
    <strong>Venue:</strong> {WORKPLACE_VENUE_NAME}, {WORKPLACE_VENUE_ADDRESS}</p>
    {party_note}{session_note}
    <p>Tea and coffee are free. Comfortable seating and sensory items are available.</p>
    <p>The session is autistic-led and low demand. In the confidential Speaking Circle, you can talk, listen, write your thoughts down or contribute anonymously.</p>
    {community_guidelines_email_html()}
    <p><a href="{calendar_url}" style="display:inline-block;background:#a92842;color:white;padding:11px 16px;border-radius:8px;text-decoration:none">Add to Google Calendar</a></p>
    <p>A calendar file is also attached for Apple Calendar, Outlook and other calendar apps.</p>
    <p style="background:#fff4f5;padding:14px;border-radius:8px"><strong>Can no longer attend?</strong><br><a href="{cancel_url}">Cancel your place</a> so somebody else can register.</p>
    <p>Warm wishes,<br><strong>LAGC Autistic Workplace Support team</strong><br>London Autism Group Charity</p>
    </body></html>"""


def upsert_film_contact(name, email, can_invite, source='Film Club booking'):
    contact = FilmContact.query.filter_by(email=email).first()
    if contact:
        if name and not contact.name:
            contact.name = name
        contact.can_invite = contact.can_invite or can_invite
    else:
        contact = FilmContact(name=name, email=email, can_invite=can_invite, source=source)
        db.session.add(contact)
    return contact

def generate_confirmation_message(name, first_name, date_display, main_course, drink, dietary_requirements, cancel_url):
    """Generate a nice HTML confirmation message"""
    
    # Build dietary line if provided
    if dietary_requirements and dietary_requirements.strip():
        dietary_line = f'<br>- Dietary Requirements: {dietary_requirements}'
    else:
        dietary_line = ''
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Tahoma, Verdana, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1a1a1a; max-width: 600px; margin: 0 auto; padding: 20px; }}
        h2 {{ color: #276749; font-size: 18px; margin-bottom: 5px; }}
        .header {{ background: #f0fff4; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #68d391; }}
        .section {{ margin-bottom: 15px; }}
        .label {{ font-weight: bold; color: #276749; }}
        .order-box {{ background: #f7fafc; padding: 12px; border-radius: 6px; margin: 10px 0; }}
        a {{ color: #276749; text-decoration: underline; }}
        a:hover {{ color: #48bb78; }}
        .cancel-link {{ background: #f0fff4; padding: 12px; border-radius: 6px; text-align: center; margin: 15px 0; }}
        .footer {{ margin-top: 25px; padding-top: 15px; border-top: 1px solid #c6f6d5; font-size: 12px; color: #4a4a4a; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>✅ Booking Confirmed!</h2>
        <p>Dear {name}, your booking for the LAGC Autistic Women's Lunch has been confirmed.</p>
    </div>

    <div class="section">
        <span class="label">Date:</span> {date_display}<br>
        <span class="label">Time:</span> 12:00 PM - 1:00 PM<br>
        <span class="label">Venue:</span> Cittie of Yorke, 22 High Holborn, London WC1V 6BN<br>
        <span class="label">Location:</span> <a href="https://maps.app.goo.gl/Wyh2E9CQU7UqpBCs9">View on Google Maps</a>
    </div>

    <div class="section">
        <span class="label">Meeting Options:</span>
        <ul>
            <li>Meet a volunteer at Holy Sepulchre Church at 11:40 AM (they will walk with you to the pub)</li>
            <li>Or meet directly at the pub at 12:00 PM</li>
        </ul>
    </div>

    <div class="section">
        <span class="label">What to expect:</span><br>
        This is a relaxed, neuroaffirming space for autistic women to connect over lunch. You can choose a main course and one non-alcoholic drink which London Autism Group Charity will be happy to cover. There is always at least one charity volunteer onsite to welcome you and help you feel comfortable.
    </div>
    
    <div class="section">
        <span class="label">Ordering:</span><br>
        You will order and select your meal directly at the pub on the day. The charity will cover your main course and one non-alcoholic drink.
        {dietary_line}
    </div>

    <div class="section">
        Self-identification is fine — you don't need a formal diagnosis.
    </div>

    <div class="cancel-link">
        <span class="label">Need to cancel?</span><br>
        <a href="{cancel_url}">Click here to cancel your booking</a>
    </div>

    <div class="footer">
        We look forward to seeing you!<br><br>
        Best regards,<br>
        <strong>LAGC Women's Lunch Team</strong><br>
        London Autism Group Charity
    </div>
</body>
</html>"""

def get_default_confirmation_message():
    """Return default confirmation message"""
    return "Your booking has been confirmed. You will receive an email with details."

def format_confirmation_message(template, **kwargs):
    """Format the confirmation message with booking details"""
    result = template
    for key, value in kwargs.items():
        if value is None:
            value = ''
        result = result.replace(f'{{{{{key}}}}}', str(value))
    return result

def send_confirmation_email(to_email, subject, html_message):
    """Send confirmation email with HTML"""
    if not app.config['ENABLE_EMAIL'] or not app.config['SMTP_USER']:
        print(f"[EMAIL WOULD BE SENT TO {to_email}]")
        print(f"Subject: {subject}")
        return True
    
    try:
        smtp_password = app.config['SMTP_PASSWORD'].replace(' ', '').replace('-', '')
        
        msg = MIMEMultipart('alternative')
        msg['From'] = app.config['SMTP_FROM']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Attach HTML version
        msg.attach(MIMEText(html_message, 'html'))
        
        with smtplib.SMTP(app.config['SMTP_HOST'], app.config['SMTP_PORT']) as server:
            server.starttls()
            server.login(app.config['SMTP_USER'], smtp_password)
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


def send_rich_email(to_email, subject, html_message, calendar_content=None):
    """Send an HTML email, optionally with a universal .ics calendar file."""
    if not app.config['ENABLE_EMAIL'] or not app.config['SMTP_USER'] or not app.config['SMTP_PASSWORD']:
        app.logger.info('Email disabled; would send %s to %s', subject, to_email)
        return False

    try:
        msg = EmailMessage()
        msg['From'] = app.config['SMTP_FROM']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.set_content('This message contains HTML. Please view it in an email application.')
        msg.add_alternative(html_message, subtype='html')
        if calendar_content:
            msg.add_attachment(
                calendar_content.encode('utf-8'),
                maintype='text', subtype='calendar', filename='autistic-film-club.ics',
                params={'method': 'PUBLISH', 'charset': 'UTF-8'},
            )
        with smtplib.SMTP(app.config['SMTP_HOST'], app.config['SMTP_PORT']) as server:
            server.starttls()
            server.login(app.config['SMTP_USER'], app.config['SMTP_PASSWORD'].replace(' ', '').replace('-', ''))
            server.send_message(msg)
        return True
    except Exception as exc:
        app.logger.exception('Failed to send email: %s', exc)
        return False


def film_confirmation_email(booking, cancel_url, calendar_url):
    film_session = booking.session_ref
    title = escape(film_session.film_title or 'Film to be announced')
    default_message = html_paragraphs(get_film_setting(
        'registration_confirmation_message', DEFAULT_FILM_CONFIRMATION_MESSAGE
    ))
    session_note = ''
    if film_session.email_message and film_session.email_message.confirmation_note:
        session_note = (
            '<div style="background:#fff7d6;border:2px solid #e6b94f;padding:14px;'
            'border-radius:8px;margin:18px 0"><strong>Important information for this session</strong><br>'
            f'{html_paragraphs(film_session.email_message.confirmation_note)}</div>'
        )
    support = booking.support_details
    party_note = ''
    if support and support.attending_with_others:
        party_note = (
            f'<p><strong>Your booking covers:</strong> you and '
            f'{support.additional_attendee_count} additional attendee'
            f'{"s" if support.additional_attendee_count != 1 else ""}.</p>'
        )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#172033;line-height:1.6;max-width:640px;margin:auto;padding:24px">
    <div style="background:#f3ecff;border-left:5px solid #6941c6;padding:18px;border-radius:10px">
      <h1 style="font-size:22px;margin:0 0 8px;color:#3d2374">Your Film Club place is confirmed</h1>
      <p style="margin:0">Hello {escape(booking.full_name)}. {default_message}</p>
    </div>
    <h2 style="font-size:18px;color:#3d2374">Session details</h2>
    <p><strong>Date:</strong> {film_session.session_date.strftime('%A %d %B %Y')}<br>
    <strong>Time:</strong> 5pm–8pm; the film begins around 5:30–5:45pm<br>
    <strong>Film:</strong> {title}<br>
    <strong>Venue:</strong> {FILM_VENUE_NAME}, {FILM_VENUE_ADDRESS}</p>
    {party_note}
    {session_note}
    <p>We expect to use the Multi Room, which has tables and chairs. A volunteer will direct you when you arrive and we will let you know if the room changes.</p>
    <p>Snacks, drinks and sensory items will be available free of charge. You are also welcome to bring your own.</p>
    <p>Our aim is to create a psychologically safe, autistic-neuroaffirming screening environment. There will always be at least two LAGC volunteers on hand throughout. After the film, volunteers will facilitate a relaxed group conversation, with no pressure to speak.</p>
    {community_guidelines_email_html()}
    <p><a href="{calendar_url}" style="display:inline-block;background:#6941c6;color:white;padding:11px 16px;border-radius:8px;text-decoration:none">Add to Google Calendar</a></p>
    <p>A calendar file is also attached for Apple Calendar, Outlook and other calendar apps.</p>
    <p style="background:#f8f6fc;padding:14px;border-radius:8px"><strong>Can no longer attend?</strong><br><a href="{cancel_url}">Cancel your place</a> so somebody else can book.</p>
    <p>Warm wishes,<br><strong>LAGC Autistic Film Club team</strong><br>London Autism Group Charity</p>
    </body></html>"""


def notify_bookers_of_film_title(film_session):
    """Email active bookers once when a title is newly announced or changed."""
    title = clean_text(film_session.film_title, 240)
    if not title:
        return 0, 0, True

    bookings = FilmBooking.query.filter_by(
        film_session_id=film_session.id, cancelled_at=None
    ).all()
    if not bookings:
        return 0, 0, True

    sent = failed = 0
    for booking in bookings:
        if FilmTitleRecipient.query.filter_by(
            film_session_id=film_session.id,
            film_title=title,
            recipient_email=booking.email,
        ).first():
            continue
        html = f"""<p>Hello {escape(booking.full_name)},</p>
        <p>The film for your Autistic Film Club session on
        <strong>{film_session.session_date.strftime('%A %d %B %Y')}</strong> has now been announced:</p>
        <p style="font-size:20px"><strong>{escape(title)}</strong></p>
        <p>Your booking remains confirmed. We look forward to seeing you from 5pm at
        {FILM_VENUE_NAME}, {FILM_VENUE_ADDRESS}.</p>
        <p>Warm wishes,<br><strong>LAGC Autistic Film Club team</strong></p>"""
        if send_rich_email(
            booking.email, f'Film announced for your Film Club session: {title}', html
        ):
            sent += 1
            db.session.add(FilmTitleRecipient(
                film_session_id=film_session.id,
                film_title=title,
                recipient_email=booking.email,
            ))
        else:
            failed += 1
    if sent:
        notification = FilmTitleNotification.query.filter_by(
            film_session_id=film_session.id, film_title=title
        ).first()
        if not notification:
            notification = FilmTitleNotification(
                film_session_id=film_session.id, film_title=title
            )
            db.session.add(notification)
        db.session.flush()
        notification.recipient_count = FilmTitleRecipient.query.filter_by(
            film_session_id=film_session.id, film_title=title
        ).count()
        db.session.commit()
    return sent, failed, False

def init_default_data():
    """Initialize default lunch dates and settings"""
    # Create lunch dates if none exist
    if LunchDate.query.count() == 0:
        for i, date_str in enumerate(LUNCH_DATES):
            lunch_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            # Only the first date is bookable initially
            is_bookable = (i == 0)
            
            ld = LunchDate(
                lunch_date=lunch_date,
                is_bookable=is_bookable,
                max_attendees=12
            )
            db.session.add(ld)
    
    # Set default confirmation message
    if not get_setting('confirmation_message'):
        set_setting('confirmation_message', get_default_confirmation_message())

    # Add the confirmed six-month Film Club schedule without disturbing any
    # sessions an administrator may already have edited.
    for date_str in FILM_SESSION_DATES:
        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if not FilmSession.query.filter_by(session_date=session_date).first():
            db.session.add(FilmSession(
                session_date=session_date,
                arrival_time=time(17, 0),
                film_start_time=time(17, 30),
                end_time=time(20, 0),
                max_attendees=15,
                is_bookable=True,
            ))

    # Keep a rolling six-month Workplace Support schedule on the last Saturday
    # of each month. Existing sessions and administrator edits are preserved.
    for session_date in next_last_saturdays(count=6):
        if not WorkplaceSession.query.filter_by(session_date=session_date).first():
            db.session.add(WorkplaceSession(
                session_date=session_date,
                start_time=time(13, 0),
                end_time=time(16, 0),
                max_attendees=15,
                is_bookable=True,
            ))
    
    db.session.commit()

def get_next_bookable_date():
    """Get the next bookable lunch date"""
    today = datetime.now().date()
    
    # Find bookable date that hasn't passed
    lunch_date = LunchDate.query.filter(
        LunchDate.is_bookable == True,
        LunchDate.lunch_date >= today
    ).order_by(LunchDate.lunch_date).first()
    
    return lunch_date

def get_all_future_dates():
    """Get all future lunch dates (for display)"""
    today = datetime.now().date()
    
    dates = LunchDate.query.filter(
        LunchDate.lunch_date >= today
    ).order_by(LunchDate.lunch_date).all()
    
    result = []
    current_bookable = None
    first_admin_bookable = None
    next_date_after_full = None
    
    for i, ld in enumerate(dates):
        # Count current bookings
        current_bookings = Booking.query.filter(
            Booking.lunch_date_id == ld.id,
            Booking.cancelled_at.is_(None)
        ).count()
        
        spots_left = ld.max_attendees - current_bookings
        is_full = spots_left <= 0
        actually_bookable = ld.is_bookable and not is_full
        
        # Track the first admin-bookable date (even if full)
        if not first_admin_bookable and ld.is_bookable:
            first_admin_bookable = {
                'id': ld.id,
                'date': ld.lunch_date.strftime('%A, %B %d, %Y'),
                'iso_date': ld.lunch_date.isoformat(),
                'week_of': (ld.lunch_date - timedelta(days=ld.lunch_date.weekday())).strftime('%B %d'),
                'is_full': is_full
            }
        
        # Track the first date that is actually bookable (has spots)
        if not current_bookable and actually_bookable:
            current_bookable = {
                'id': ld.id,
                'date': ld.lunch_date.strftime('%A, %B %d, %Y'),
                'iso_date': ld.lunch_date.isoformat(),
                'week_of': (ld.lunch_date - timedelta(days=ld.lunch_date.weekday())).strftime('%B %d')
            }
        
        # Track the next date chronologically after the first admin-bookable one
        # This is for when the first date is full - we want to show the next one
        if first_admin_bookable and not next_date_after_full and ld.id != first_admin_bookable['id']:
            next_date_after_full = {
                'id': ld.id,
                'date': ld.lunch_date.strftime('%A, %B %d, %Y'),
                'iso_date': ld.lunch_date.isoformat(),
                'week_of': (ld.lunch_date - timedelta(days=ld.lunch_date.weekday())).strftime('%B %d')
            }
        
        result.append({
            'id': ld.id,
            'date': ld.lunch_date.isoformat(),
            'display': ld.lunch_date.strftime('%A, %B %d, %Y'),
            'admin_bookable': ld.is_bookable,  # Whether admin marked it as bookable
            'is_bookable': actually_bookable,  # Actually bookable (has spots)
            'spots_left': spots_left,
            'is_full': is_full
        })
    
    # Add bookable date info to the first item (for frontend use)
    if result:
        if current_bookable:
            result[0]['current_bookable'] = current_bookable
        if first_admin_bookable:
            result[0]['first_admin_bookable'] = first_admin_bookable
        if next_date_after_full:
            result[0]['next_date_after_full'] = next_date_after_full
    
    return result

# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def landing():
    """Gateway to LAGC activity websites."""
    return render_template('gateway.html')


@app.route('/womens-lunch')
def womens_lunch_landing():
    """Existing Women's Lunch landing page."""
    return render_template('landing.html')

@app.route('/womens-lunch/book')
@app.route('/book')
def book():
    """Booking page"""
    return render_template('book.html')

@app.route('/admin')
def admin():
    """Preserve the Women's Lunch administration at its original URL."""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login', next=url_for('womens_lunch_admin')))
    return redirect(url_for('womens_lunch_admin'))


@app.route('/admin/womens-lunch')
def womens_lunch_admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login', next=url_for('womens_lunch_admin')))
    return render_template('admin.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    next_url = request.form.get('next') or request.args.get('next') or url_for('womens_lunch_admin')
    allowed_destinations = {
        url_for('admin'), url_for('film_club_admin'), url_for('womens_lunch_admin'),
        url_for('workplace_admin'),
    }
    if next_url not in allowed_destinations:
        next_url = url_for('womens_lunch_admin')
    is_workplace_login = next_url == url_for('workplace_admin')
    if is_workplace_login and session.get('workplace_admin_logged_in'):
        return redirect(next_url)
    if not is_workplace_login and session.get('admin_logged_in'):
        return redirect(next_url)
    
    error = None
    if request.method == 'POST':
        require_csrf()
        password = request.form.get('password', '')
        expected_password = (
            app.config['WORKPLACE_ADMIN_PASSWORD']
            if is_workplace_login else app.config['ADMIN_PASSWORD']
        )
        if secrets.compare_digest(password, expected_password):
            if is_workplace_login:
                session['workplace_admin_logged_in'] = True
            else:
                session['admin_logged_in'] = True
            session.permanent = True
            csrf_token()
            return redirect(next_url)
        else:
            error = 'Invalid password'
    
    return render_template('admin_login.html', error=error, next_url=next_url)

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('workplace_admin_logged_in', None)
    return redirect(url_for('landing'))

@app.route('/cancel/<token>')
@app.route('/womens-lunch/cancel/<token>')
def cancel_page(token):
    """Cancellation page"""
    return render_template('cancel.html', token=token)

@app.route('/access')
@app.route('/womens-lunch/access')
def access_gate():
    """Access code gate page"""
    return render_template('access.html')


# ============================================================================
# AUTISTIC FILM CLUB - PUBLIC ROUTES
# ============================================================================

@app.route('/film-club')
def film_club_home():
    sessions = FilmSession.query.filter(
        FilmSession.session_date >= datetime.now().date()
    ).order_by(FilmSession.session_date).all()
    return render_template(
        'film_home.html',
        session_cards=[film_session_summary(item) for item in sessions],
        venue_name=FILM_VENUE_NAME,
        venue_address=FILM_VENUE_ADDRESS,
        map_url=FILM_MAP_URL,
        news_items=FilmNewsItem.query.filter_by(is_active=True).order_by(
            FilmNewsItem.sort_order, FilmNewsItem.id
        ).all(),
    )


@app.route('/film-club/book/<int:session_id>', methods=['GET', 'POST'])
def film_club_book(session_id):
    film_session = FilmSession.query.get_or_404(session_id)
    summary = film_session_summary(film_session)
    if request.method == 'GET':
        return render_template('film_book.html', film_session=film_session, summary=summary)

    require_csrf()
    if request.form.get('is_adult') != 'yes':
        return render_template('film_under18.html'), 400

    full_name = clean_text(request.form.get('full_name'), 200)
    email = valid_email(request.form.get('email'))
    phone = clean_text(request.form.get('phone'), 40)
    attending_with = request.form.get('attending_with_others')
    support_acknowledged = request.form.get('support_boundary_acknowledged') == 'on'
    if not full_name or not email or not phone:
        flash('Please provide your name, email address and phone number.', 'error')
        return render_template('film_book.html', film_session=film_session, summary=summary), 400
    if attending_with not in {'yes', 'no'}:
        flash('Please tell us whether anyone else will attend with you.', 'error')
        return render_template('film_book.html', film_session=film_session, summary=summary), 400
    if not support_acknowledged:
        flash('Please confirm that you understand what our volunteers can and cannot provide.', 'error')
        return render_template('film_book.html', film_session=film_session, summary=summary), 400

    attending_with_others = attending_with == 'yes'
    additional_count = 0
    companion_details = ''
    has_carer = False
    carer_name = carer_organisation = carer_mobile = responsibility_details = ''
    if attending_with_others:
        try:
            additional_count = int(request.form.get('additional_attendee_count', ''))
        except (TypeError, ValueError):
            additional_count = 0
        companion_details = clean_text(request.form.get('companion_details'), 3000)
        carer_answer = request.form.get('has_carer_or_support_worker')
        responsibility_details = clean_text(request.form.get('responsibility_details'), 3000)
        if additional_count < 1 or additional_count > 10 or not companion_details:
            flash('Please tell us who will attend with you and how many people are coming.', 'error')
            return render_template('film_book.html', film_session=film_session, summary=summary), 400
        if carer_answer not in {'yes', 'no'} or not responsibility_details:
            flash('Please complete the support and responsibility questions.', 'error')
            return render_template('film_book.html', film_session=film_session, summary=summary), 400
        has_carer = carer_answer == 'yes'
        if has_carer:
            carer_name = clean_text(request.form.get('carer_name'), 200)
            carer_organisation = clean_text(request.form.get('carer_organisation'), 240)
            carer_mobile = clean_text(request.form.get('carer_mobile'), 40)
            if not all([carer_name, carer_organisation, carer_mobile]):
                flash('Please provide the carer or support worker’s contact details.', 'error')
                return render_template('film_book.html', film_session=film_session, summary=summary), 400
    if film_session.session_date < datetime.now().date() or not film_session.is_bookable:
        flash('This session is not currently open for booking.', 'error')
        return redirect(url_for('film_club_home'))

    party_size = 1 + additional_count
    refreshed_summary = film_session_summary(film_session)
    if party_size > refreshed_summary['places_left']:
        flash(
            f'There are only {refreshed_summary["places_left"]} places left, which is not enough '
            f'for your group of {party_size}.', 'error'
        )
        return redirect(url_for('film_club_home'))
    existing = FilmBooking.query.filter_by(
        film_session_id=film_session.id, email=email, cancelled_at=None
    ).first()
    if existing:
        flash('That email address already has a place for this session.', 'error')
        return redirect(url_for('film_club_home'))

    booking = FilmBooking(
        film_session_id=film_session.id,
        full_name=full_name,
        email=email,
        is_adult=True,
        access_needs=clean_text(request.form.get('access_needs'), 3000),
        seating_preferences=clean_text(request.form.get('seating_preferences'), 2000),
        comfort_information=clean_text(request.form.get('comfort_information'), 3000),
        dietary_requirements=clean_text(request.form.get('dietary_requirements'), 2000),
        interested_in_nominating=request.form.get('interested_in_nominating') == 'yes',
        future_updates_opt_in=request.form.get('future_updates_opt_in') == 'on',
        cancel_token=secrets.token_urlsafe(32),
    )
    db.session.add(booking)
    db.session.flush()
    db.session.add(FilmBookingSupport(
        film_booking_id=booking.id,
        attendee_phone=phone,
        attending_with_others=attending_with_others,
        additional_attendee_count=additional_count,
        companion_details=companion_details or None,
        has_carer_or_support_worker=has_carer,
        carer_name=carer_name or None,
        carer_organisation=carer_organisation or None,
        carer_mobile=carer_mobile or None,
        responsibility_details=responsibility_details or None,
        support_boundary_acknowledged=True,
    ))
    upsert_film_contact(full_name, email, booking.future_updates_opt_in)
    db.session.commit()

    cancel_url = url_for('film_club_cancel', token=booking.cancel_token, _external=True)
    calendar_url = google_calendar_url(film_session)
    sent = send_rich_email(
        booking.email,
        film_confirmation_subject(film_session),
        film_confirmation_email(booking, cancel_url, calendar_url),
        film_calendar_ics(film_session, booking),
    )
    admin_html = f"""<p><strong>New Film Club booking</strong></p>
    <p>{escape(booking.full_name)} ({escape(booking.email)} · {escape(phone)})<br>
    {film_session.session_date.strftime('%A %d %B %Y')}</p>
    <p><strong>Party size:</strong> {party_size}<br>
    <strong>Attending with:</strong> {escape(companion_details or 'Nobody else')}<br>
    <strong>Carer/support worker:</strong> {escape(carer_name or 'No')} {escape(carer_mobile or '')}<br>
    <strong>Responsibility:</strong> {escape(responsibility_details or 'Attending alone')}</p>
    <p><strong>Access/sensory needs:</strong> {escape(booking.access_needs or 'None provided')}<br>
    <strong>Seating:</strong> {escape(booking.seating_preferences or 'None provided')}<br>
    <strong>Comfort information:</strong> {escape(booking.comfort_information or 'None provided')}<br>
    <strong>Dietary/allergies:</strong> {escape(booking.dietary_requirements or 'None provided')}</p>"""
    send_rich_email(
        app.config['ADMIN_EMAIL'],
        f'New Film Club booking: {booking.full_name}',
        admin_html,
    )
    if booking.interested_in_nominating:
        flash(
            'Your Film Club place is booked. You can now tell us which film you would like to nominate.',
            'success',
        )
        return redirect(url_for('film_club_nominate', from_booking='yes'))
    return render_template(
        'film_confirmation.html', booking=booking,
        calendar_url=calendar_url, email_sent=sent,
    )


@app.route('/film-club/calendar/<token>.ics')
def film_club_calendar(token):
    booking = FilmBooking.query.filter_by(cancel_token=token).first_or_404()
    return Response(
        film_calendar_ics(booking.session_ref, booking),
        mimetype='text/calendar',
        headers={'Content-Disposition': 'attachment; filename=autistic-film-club.ics'},
    )


@app.route('/film-club/cancel/<token>', methods=['GET', 'POST'])
def film_club_cancel(token):
    booking = FilmBooking.query.filter_by(cancel_token=token).first_or_404()
    if request.method == 'POST':
        require_csrf()
        if not booking.cancelled_at:
            booking.cancelled_at = datetime.utcnow()
            db.session.commit()
            send_rich_email(
                app.config['ADMIN_EMAIL'],
                f'Film Club cancellation: {booking.full_name}',
                f'<p>{escape(booking.full_name)} has cancelled their place for '
                f'{booking.session_ref.session_date.strftime("%A %d %B %Y")}.</p>',
            )
            send_rich_email(
                booking.email,
                'Your Film Club booking has been cancelled',
                f'<p>Hello {escape(booking.full_name)},</p><p>Your place for the Autistic Film Club on '
                f'{booking.session_ref.session_date.strftime("%A %d %B %Y")} has been cancelled.</p>'
                '<p>Thank you for letting us know.<br>London Autism Group Charity</p>',
            )
        return render_template('film_cancelled.html', booking=booking)
    return render_template('film_cancel.html', booking=booking)


@app.route('/film-club/nominate', methods=['GET', 'POST'])
def film_club_nominate():
    if request.method == 'GET':
        return render_template(
            'film_nominate.html',
            from_booking=request.args.get('from_booking') == 'yes',
        )
    require_csrf()
    if request.form.get('is_adult') != 'yes':
        return render_template('film_under18.html'), 400

    name = clean_text(request.form.get('nominator_name'), 200)
    email = valid_email(request.form.get('nominator_email'))
    film_title = clean_text(request.form.get('film_title'), 240)
    why_this_film = clean_text(request.form.get('why_this_film'), 4000)
    if not all([name, email, film_title, why_this_film]):
        flash('Please complete your name, email, film title and why you chose it.', 'error')
        return render_template('film_nominate.html'), 400

    nomination = FilmNomination(
        nominator_name=name,
        nominator_email=email,
        film_title=film_title,
        why_this_film=why_this_film,
        introduction_notes=clean_text(request.form.get('introduction_notes'), 4000),
        can_introduce=request.form.get('can_introduce') == 'yes',
        availability_notes=clean_text(request.form.get('availability_notes'), 2000),
        content_notes=clean_text(request.form.get('content_notes'), 3000),
    )
    db.session.add(nomination)
    db.session.commit()
    send_rich_email(
        app.config['ADMIN_EMAIL'],
        f'New Film Club nomination: {film_title}',
        f'<p><strong>{escape(film_title)}</strong> was nominated by '
        f'{escape(name)} ({escape(email)}).</p><p>{escape(why_this_film)}</p>',
    )
    send_rich_email(
        nomination.nominator_email,
        f'We received your Film Club nomination: {film_title}',
        f'<p>Hello {escape(name)},</p><p>Thank you for nominating <strong>{escape(film_title)}</strong> '
        'for the LAGC Autistic Film Club.</p><p>Our team will review it while planning future months. '
        'If it is selected, we will contact you about the date and how you would like it introduced.</p>'
        '<p>London Autism Group Charity</p>',
    )
    return render_template('film_nomination_thanks.html', nomination=nomination)


# ============================================================================
# AUTISTIC FILM CLUB - ADMIN ROUTES
# ============================================================================

@app.route('/admin/film-club')
@admin_required
def film_club_admin():
    sessions = FilmSession.query.order_by(FilmSession.session_date).all()
    bookings = FilmBooking.query.join(FilmSession).order_by(
        FilmSession.session_date, FilmBooking.full_name
    ).all()
    nominations = FilmNomination.query.order_by(FilmNomination.created_at.desc()).all()
    contacts = FilmContact.query.order_by(FilmContact.email).all()
    news_items = FilmNewsItem.query.order_by(FilmNewsItem.sort_order, FilmNewsItem.id).all()
    return render_template(
        'film_admin.html',
        session_cards=[film_session_summary(item) for item in sessions],
        bookings=bookings, nominations=nominations, contacts=contacts,
        news_items=news_items,
        confirmation_subject=get_film_setting(
            'registration_confirmation_subject', 'Film Club booking confirmed - {date}'
        ),
        confirmation_message=get_film_setting(
            'registration_confirmation_message', DEFAULT_FILM_CONFIRMATION_MESSAGE
        ),
    )


@app.route('/admin/film-club/session/<int:session_id>', methods=['POST'])
@admin_required
def film_admin_update_session(session_id):
    require_csrf()
    film_session = FilmSession.query.get_or_404(session_id)
    previous_title = film_session.film_title
    film_session.film_title = clean_text(request.form.get('film_title'), 240) or None
    film_session.film_details = clean_text(request.form.get('film_details'), 3000) or None
    try:
        film_session.max_attendees = max(1, min(100, int(request.form.get('max_attendees', 15))))
    except ValueError:
        film_session.max_attendees = 15
    film_session.is_bookable = request.form.get('is_bookable') == 'on'
    db.session.commit()
    if film_session.film_title:
        sent, failed, skipped = notify_bookers_of_film_title(film_session)
        if sent or failed:
            flash(
                f'Session updated. Film announcement emails: {sent} sent, {failed} failed.',
                'success' if not failed else 'error',
            )
        elif previous_title == film_session.film_title:
            flash('Session updated. Everyone already received this film announcement.', 'success')
        else:
            flash('Session updated. There were no existing bookers to notify.', 'success')
    else:
        flash('Session updated.', 'success')
    return redirect(url_for('film_club_admin', tab='sessions'))


@app.route('/admin/film-club/nomination/<int:nomination_id>', methods=['POST'])
@admin_required
def film_admin_update_nomination(nomination_id):
    require_csrf()
    nomination = FilmNomination.query.get_or_404(nomination_id)
    status = request.form.get('status', 'new')
    if status not in {'new', 'considering', 'selected', 'screened', 'declined'}:
        abort(400)
    nomination.status = status
    selected_id = request.form.get('selected_session_id', type=int)
    nomination.selected_session_id = selected_id if selected_id else None
    selected_session = None
    previous_title = None
    if status == 'selected' and selected_id:
        selected_session = FilmSession.query.get_or_404(selected_id)
        previous_title = selected_session.film_title
        selected_session.film_title = nomination.film_title
    db.session.commit()
    if selected_session:
        sent, failed, skipped = notify_bookers_of_film_title(selected_session)
        flash(
            f'Nomination updated. Film announcement emails: {sent} sent, {failed} failed.',
            'success' if not failed else 'error',
        )
    else:
        flash('Nomination updated.', 'success')
    return redirect(url_for('film_club_admin', tab='nominations'))


@app.route('/admin/film-club/volunteer', methods=['POST'])
@admin_required
def film_admin_add_volunteer():
    require_csrf()
    film_session = FilmSession.query.get_or_404(request.form.get('film_session_id', type=int))
    name = clean_text(request.form.get('volunteer_name'), 200)
    if not name:
        flash('A volunteer name is required.', 'error')
        return redirect(url_for('film_club_admin', tab='rota'))
    db.session.add(FilmVolunteer(
        film_session_id=film_session.id,
        volunteer_name=name,
        volunteer_email=valid_email(request.form.get('volunteer_email')),
        role=clean_text(request.form.get('role'), 120) or 'Session volunteer',
        notes=clean_text(request.form.get('notes'), 2000),
    ))
    db.session.commit()
    flash('Volunteer added to the rota.', 'success')
    return redirect(url_for('film_club_admin', tab='rota'))


@app.route('/admin/film-club/volunteer/<int:volunteer_id>/delete', methods=['POST'])
@admin_required
def film_admin_delete_volunteer(volunteer_id):
    require_csrf()
    assignment = FilmVolunteer.query.get_or_404(volunteer_id)
    db.session.delete(assignment)
    db.session.commit()
    flash('Volunteer assignment removed.', 'success')
    return redirect(url_for('film_club_admin', tab='rota'))


@app.route('/admin/film-club/contacts/import', methods=['POST'])
@admin_required
def film_admin_import_contacts():
    require_csrf()
    if request.form.get('permission_confirmed') != 'on':
        flash('Confirm that these contacts may receive Film Club invitations.', 'error')
        return redirect(url_for('film_club_admin', tab='contacts'))
    imported = 0
    reader = csv.reader(io.StringIO(request.form.get('contacts', '')))
    for row in reader:
        if not row:
            continue
        if len(row) == 1:
            name, raw_email = '', row[0]
        else:
            name, raw_email = row[0], row[1]
        email = valid_email(raw_email)
        if email:
            upsert_film_contact(clean_text(name, 200), email, True, 'Past Film Club attendee import')
            imported += 1
    db.session.commit()
    flash(f'{imported} contact row(s) imported or updated.', 'success')
    return redirect(url_for('film_club_admin', tab='contacts'))


@app.route('/admin/film-club/invite', methods=['POST'])
@admin_required
def film_admin_invite_contacts():
    require_csrf()
    film_session = FilmSession.query.get_or_404(request.form.get('film_session_id', type=int))
    if film_session.invitation_run:
        flash('The one-off invitation has already been sent for this session.', 'error')
        return redirect(url_for('film_club_admin', tab='contacts'))
    if request.form.get('send_confirmed') != 'on':
        flash('Tick the confirmation box before sending invitations.', 'error')
        return redirect(url_for('film_club_admin', tab='contacts'))
    invitation_run = FilmInvitationRun(
        film_session_id=film_session.id, sent_count=0, failed_count=0
    )
    db.session.add(invitation_run)
    db.session.commit()
    booking_url = url_for('film_club_book', session_id=film_session.id, _external=True)
    already_booked = {
        item.email for item in FilmBooking.query.filter_by(
            film_session_id=film_session.id, cancelled_at=None
        ).all()
    }
    sent = failed = 0
    for contact in FilmContact.query.filter_by(can_invite=True).all():
        if contact.email in already_booked:
            continue
        greeting = f'Hello {escape(contact.name)},' if contact.name else 'Hello,'
        html = f"""<p>{greeting}</p><p>Places are available for the LAGC Autistic Film Club on
        <strong>{film_session.session_date.strftime('%A %d %B %Y')}</strong>, 5pm–8pm at
        {FILM_VENUE_NAME}.</p><p><a href="{booking_url}">View the session and book a place</a></p>
        <p>London Autism Group Charity</p>"""
        if send_rich_email(contact.email, 'Autistic Film Club - places available', html):
            sent += 1
            contact.last_invited_at = datetime.utcnow()
        else:
            failed += 1
    invitation_run.sent_count = sent
    invitation_run.failed_count = failed
    db.session.commit()
    flash(f'Invitations processed: {sent} sent, {failed} failed.', 'success' if not failed else 'error')
    return redirect(url_for('film_club_admin', tab='contacts'))


@app.route('/admin/film-club/email-settings', methods=['POST'])
@admin_required
def film_admin_email_settings():
    require_csrf()
    subject = clean_text(request.form.get('confirmation_subject'), 240)
    message = clean_text(request.form.get('confirmation_message'), 5000)
    if not subject or not message:
        flash('The confirmation subject and message cannot be blank.', 'error')
        return redirect(url_for('film_club_admin', tab='emails'))
    set_film_setting('registration_confirmation_subject', subject)
    set_film_setting('registration_confirmation_message', message)
    db.session.commit()
    flash('Default Film Club confirmation email updated.', 'success')
    return redirect(url_for('film_club_admin', tab='emails'))


@app.route('/admin/film-club/session/<int:session_id>/email-message', methods=['POST'])
@admin_required
def film_admin_session_email_message(session_id):
    require_csrf()
    film_session = FilmSession.query.get_or_404(session_id)
    note = clean_text(request.form.get('confirmation_note'), 5000)
    message = film_session.email_message
    if note:
        if message:
            message.confirmation_note = note
        else:
            db.session.add(FilmSessionMessage(
                film_session_id=film_session.id, confirmation_note=note
            ))
    elif message:
        db.session.delete(message)
    db.session.commit()
    flash('Session-specific confirmation note saved.', 'success')
    return redirect(url_for('film_club_admin', tab='emails'))


def normalise_news_link(raw_url, raw_text):
    link_url = clean_text(raw_url, 1000)
    link_text = clean_text(raw_text, 160)
    if not link_url and not link_text:
        return None, None
    if not link_url or not link_text or not (
        link_url.startswith('https://') or link_url.startswith('http://') or link_url.startswith('/')
    ):
        return None
    return link_url, link_text


@app.route('/admin/film-club/news', methods=['POST'])
@admin_required
def film_admin_add_news():
    require_csrf()
    headline = clean_text(request.form.get('headline'), 240)
    link = normalise_news_link(request.form.get('link_url'), request.form.get('link_text'))
    if not headline:
        flash('A news headline is required.', 'error')
        return redirect(url_for('film_club_admin', tab='news'))
    if link is None:
        flash('For a news link, provide both valid link URL and link text.', 'error')
        return redirect(url_for('film_club_admin', tab='news'))
    next_order = (db.session.query(db.func.max(FilmNewsItem.sort_order)).scalar() or 0) + 1
    db.session.add(FilmNewsItem(
        emoji=clean_text(request.form.get('emoji'), 20),
        headline=headline,
        details=clean_text(request.form.get('details'), 2000),
        link_url=link[0], link_text=link[1], sort_order=next_order,
        is_active=request.form.get('is_active') == 'on',
    ))
    db.session.commit()
    flash('News item added to the Film Club ticker.', 'success')
    return redirect(url_for('film_club_admin', tab='news'))


@app.route('/admin/film-club/news/<int:news_id>', methods=['POST'])
@admin_required
def film_admin_update_news(news_id):
    require_csrf()
    item = FilmNewsItem.query.get_or_404(news_id)
    headline = clean_text(request.form.get('headline'), 240)
    link = normalise_news_link(request.form.get('link_url'), request.form.get('link_text'))
    if not headline or link is None:
        flash('Use a headline and complete both link fields if adding a link.', 'error')
        return redirect(url_for('film_club_admin', tab='news'))
    item.emoji = clean_text(request.form.get('emoji'), 20)
    item.headline = headline
    item.details = clean_text(request.form.get('details'), 2000)
    item.link_url, item.link_text = link
    item.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    flash('News item updated.', 'success')
    return redirect(url_for('film_club_admin', tab='news'))


@app.route('/admin/film-club/news/<int:news_id>/delete', methods=['POST'])
@admin_required
def film_admin_delete_news(news_id):
    require_csrf()
    db.session.delete(FilmNewsItem.query.get_or_404(news_id))
    db.session.commit()
    flash('News item deleted.', 'success')
    return redirect(url_for('film_club_admin', tab='news'))


@app.route('/admin/film-club/news/<int:news_id>/move/<direction>', methods=['POST'])
@admin_required
def film_admin_move_news(news_id, direction):
    require_csrf()
    if direction not in {'up', 'down'}:
        abort(400)
    items = FilmNewsItem.query.order_by(FilmNewsItem.sort_order, FilmNewsItem.id).all()
    item = FilmNewsItem.query.get_or_404(news_id)
    index = next((i for i, candidate in enumerate(items) if candidate.id == item.id), None)
    target_index = index - 1 if direction == 'up' else index + 1
    if index is not None and 0 <= target_index < len(items):
        other = items[target_index]
        item.sort_order, other.sort_order = other.sort_order, item.sort_order
        if item.sort_order == other.sort_order:
            item.sort_order, other.sort_order = target_index, index
        db.session.commit()
    return redirect(url_for('film_club_admin', tab='news'))


@app.route('/admin/film-club/bookings.csv')
@admin_required
def film_admin_bookings_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Session date', 'Name', 'Email', 'Phone', 'Status', 'Party size',
        'Attending with', 'Carer or support worker', 'Carer organisation',
        'Carer mobile', 'Responsibility or supervision details', 'Access or sensory needs',
        'Seating preferences', 'Comfort information', 'Dietary requirements',
        'Interested in nominating', 'Future updates opt-in', 'Booked at',
    ])
    bookings = FilmBooking.query.join(FilmSession).order_by(FilmSession.session_date).all()
    for item in bookings:
        support = item.support_details
        writer.writerow([
            item.session_ref.session_date.isoformat(), item.full_name, item.email,
            support.attendee_phone if support else '',
            'Cancelled' if item.cancelled_at else 'Active', booking_party_size(item),
            support.companion_details if support else '',
            support.carer_name if support else '', support.carer_organisation if support else '',
            support.carer_mobile if support else '', support.responsibility_details if support else '',
            item.access_needs,
            item.seating_preferences, item.comfort_information, item.dietary_requirements,
            'Yes' if item.interested_in_nominating else 'No',
            'Yes' if item.future_updates_opt_in else 'No', item.created_at.isoformat(),
        ])
    return Response(
        output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=film-club-bookings.csv'},
    )


# ============================================================================
# AUTISTIC WORKPLACE SUPPORT - PUBLIC ROUTES
# ============================================================================

@app.route('/workplace-support')
def workplace_home():
    sessions = WorkplaceSession.query.filter(
        WorkplaceSession.session_date >= datetime.now().date()
    ).order_by(WorkplaceSession.session_date).all()
    return render_template(
        'workplace_home.html',
        session_cards=[workplace_session_summary(item) for item in sessions],
        venue_name=WORKPLACE_VENUE_NAME,
        venue_address=WORKPLACE_VENUE_ADDRESS,
        map_url=WORKPLACE_MAP_URL,
        news_items=WorkplaceNewsItem.query.filter_by(is_active=True).order_by(
            WorkplaceNewsItem.sort_order, WorkplaceNewsItem.id
        ).all(),
    )


@app.route('/workplace-support/register/<int:session_id>', methods=['GET', 'POST'])
def workplace_book(session_id):
    workplace_session = WorkplaceSession.query.get_or_404(session_id)
    summary = workplace_session_summary(workplace_session)
    if request.method == 'GET':
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        )

    require_csrf()
    if request.form.get('is_adult') != 'yes':
        return render_template('workplace_under18.html'), 400

    full_name = clean_text(request.form.get('full_name'), 200)
    email = valid_email(request.form.get('email'))
    phone = clean_text(request.form.get('phone'), 40)
    attend_mentoring = request.form.get('attend_mentoring') == 'on'
    attend_group = request.form.get('attend_group_discussion') == 'on'
    attending_with = request.form.get('attending_with_others')
    if not all([full_name, email, phone]):
        flash('Please provide your name, email address and phone number.', 'error')
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        ), 400
    if not attend_mentoring and not attend_group:
        flash('Please select at least one part of the session.', 'error')
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        ), 400
    if attend_group and request.form.get('confidentiality_commitment') != 'on':
        flash('Please agree to the Speaking Circle confidentiality commitment.', 'error')
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        ), 400
    if attending_with not in {'yes', 'no'}:
        flash('Please tell us whether anyone else will attend with you.', 'error')
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        ), 400
    if request.form.get('support_boundary_acknowledged') != 'on':
        flash('Please confirm that you understand the volunteer and mentor support boundaries.', 'error')
        return render_template(
            'workplace_book.html', workplace_session=workplace_session, summary=summary
        ), 400
    if workplace_session.session_date < datetime.now().date() or not workplace_session.is_bookable:
        flash('This session is not currently open for registration.', 'error')
        return redirect(url_for('workplace_home'))

    attending_with_others = attending_with == 'yes'
    additional_count = 0
    companion_details = ''
    has_carer = False
    carer_name = carer_organisation = carer_mobile = responsibility_details = ''
    if attending_with_others:
        try:
            additional_count = int(request.form.get('additional_attendee_count', ''))
        except (TypeError, ValueError):
            additional_count = 0
        companion_details = clean_text(request.form.get('companion_details'), 3000)
        carer_answer = request.form.get('has_carer_or_support_worker')
        responsibility_details = clean_text(request.form.get('responsibility_details'), 3000)
        if additional_count < 1 or additional_count > 10 or not companion_details:
            flash('Please tell us who will attend with you and how many people are coming.', 'error')
            return render_template(
                'workplace_book.html', workplace_session=workplace_session, summary=summary
            ), 400
        if carer_answer not in {'yes', 'no'} or not responsibility_details:
            flash('Please complete the support and responsibility questions.', 'error')
            return render_template(
                'workplace_book.html', workplace_session=workplace_session, summary=summary
            ), 400
        has_carer = carer_answer == 'yes'
        if has_carer:
            carer_name = clean_text(request.form.get('carer_name'), 200)
            carer_organisation = clean_text(request.form.get('carer_organisation'), 240)
            carer_mobile = clean_text(request.form.get('carer_mobile'), 40)
            if not all([carer_name, carer_organisation, carer_mobile]):
                flash('Please provide the carer or support worker’s contact details.', 'error')
                return render_template(
                    'workplace_book.html', workplace_session=workplace_session, summary=summary
                ), 400

    party_size = 1 + additional_count
    refreshed = workplace_session_summary(workplace_session)
    if party_size > refreshed['places_left']:
        flash(
            f'There are only {refreshed["places_left"]} places left, which is not enough '
            f'for your group of {party_size}.', 'error'
        )
        return redirect(url_for('workplace_home'))
    if WorkplaceBooking.query.filter_by(
        workplace_session_id=workplace_session.id, email=email, cancelled_at=None
    ).first():
        flash('That email address already has a registration for this session.', 'error')
        return redirect(url_for('workplace_home'))

    attended_answer = request.form.get('attended_before')
    booking = WorkplaceBooking(
        workplace_session_id=workplace_session.id,
        full_name=full_name, email=email, phone=phone, is_adult=True,
        attend_mentoring=attend_mentoring,
        attend_group_discussion=attend_group,
        attended_before=True if attended_answer == 'yes' else False if attended_answer == 'no' else None,
        support_hoped_for=clean_text(request.form.get('support_hoped_for'), 4000),
        access_needs=clean_text(request.form.get('access_needs'), 3000),
        dietary_requirements=clean_text(request.form.get('dietary_requirements'), 2000),
        additional_information=clean_text(request.form.get('additional_information'), 3000),
        attending_with_others=attending_with_others,
        additional_attendee_count=additional_count,
        companion_details=companion_details or None,
        has_carer_or_support_worker=has_carer,
        carer_name=carer_name or None,
        carer_organisation=carer_organisation or None,
        carer_mobile=carer_mobile or None,
        responsibility_details=responsibility_details or None,
        support_boundary_acknowledged=True,
        cancel_token=secrets.token_urlsafe(32),
    )
    db.session.add(booking)
    db.session.commit()

    cancel_url = url_for('workplace_cancel', token=booking.cancel_token, _external=True)
    calendar_url = workplace_google_calendar_url(workplace_session, booking)
    subject_template = get_workplace_setting(
        'registration_confirmation_subject', 'Workplace Support registration confirmed - {date}'
    )
    subject = subject_template.replace(
        '{date}', workplace_session.session_date.strftime('%d %B %Y')
    )[:240]
    sent = send_rich_email(
        booking.email, subject,
        workplace_confirmation_email(booking, cancel_url, calendar_url),
        workplace_calendar_ics(workplace_session, booking),
    )
    admin_html = f"""<p><strong>New Workplace Support registration</strong></p>
    <p>{escape(booking.full_name)} · {escape(booking.email)} · {escape(booking.phone)}<br>
    {workplace_session.session_date.strftime('%A %d %B %Y')} · {party_size} place(s)</p>
    <p><strong>Mentoring:</strong> {'Yes' if attend_mentoring else 'No'}<br>
    <strong>Speaking Circle:</strong> {'Yes' if attend_group else 'No'}<br>
    <strong>Hoping for:</strong> {escape(booking.support_hoped_for or 'Not provided')}</p>
    <p><strong>Attending with:</strong> {escape(companion_details or 'Nobody else')}<br>
    <strong>Carer/support worker:</strong> {escape(carer_name or 'No')} {escape(carer_mobile or '')}<br>
    <strong>Responsibility:</strong> {escape(responsibility_details or 'Attending alone')}</p>
    <p><strong>Access/sensory:</strong> {escape(booking.access_needs or 'None provided')}<br>
    <strong>Dietary/allergies:</strong> {escape(booking.dietary_requirements or 'None provided')}<br>
    <strong>Other information:</strong> {escape(booking.additional_information or 'None provided')}</p>"""
    send_rich_email(
        app.config['ADMIN_EMAIL'], f'New Workplace Support registration: {booking.full_name}', admin_html
    )
    return render_template(
        'workplace_confirmation.html', booking=booking,
        calendar_url=calendar_url, email_sent=sent,
    )


@app.route('/workplace-support/calendar/<token>.ics')
def workplace_calendar(token):
    booking = WorkplaceBooking.query.filter_by(cancel_token=token).first_or_404()
    return Response(
        workplace_calendar_ics(booking.session_ref, booking),
        mimetype='text/calendar',
        headers={'Content-Disposition': 'attachment; filename=autistic-workplace-support.ics'},
    )


@app.route('/workplace-support/cancel/<token>', methods=['GET', 'POST'])
def workplace_cancel(token):
    booking = WorkplaceBooking.query.filter_by(cancel_token=token).first_or_404()
    if request.method == 'POST':
        require_csrf()
        if not booking.cancelled_at:
            booking.cancelled_at = datetime.utcnow()
            db.session.commit()
            send_rich_email(
                app.config['ADMIN_EMAIL'],
                f'Workplace Support cancellation: {booking.full_name}',
                f'<p>{escape(booking.full_name)} cancelled their registration for '
                f'{booking.session_ref.session_date.strftime("%A %d %B %Y")}.</p>',
            )
            send_rich_email(
                booking.email, 'Your Workplace Support registration has been cancelled',
                f'<p>Hello {escape(booking.full_name)},</p><p>Your registration for '
                f'{booking.session_ref.session_date.strftime("%A %d %B %Y")} has been cancelled.</p>'
                '<p>Thank you for letting us know.<br>London Autism Group Charity</p>',
            )
        return render_template('workplace_cancelled.html', booking=booking)
    return render_template('workplace_cancel.html', booking=booking)


# ============================================================================
# AUTISTIC WORKPLACE SUPPORT - ADMIN ROUTES
# ============================================================================

@app.route('/admin/workplace-support')
@workplace_admin_required
def workplace_admin():
    sessions = WorkplaceSession.query.order_by(WorkplaceSession.session_date).all()
    bookings = WorkplaceBooking.query.join(WorkplaceSession).order_by(
        WorkplaceSession.session_date, WorkplaceBooking.full_name
    ).all()
    contacts = WorkplaceContact.query.order_by(WorkplaceContact.email).all()
    news_items = WorkplaceNewsItem.query.order_by(
        WorkplaceNewsItem.sort_order, WorkplaceNewsItem.id
    ).all()
    return render_template(
        'workplace_admin.html',
        session_cards=[workplace_session_summary(item) for item in sessions],
        bookings=bookings,
        contacts=contacts,
        news_items=news_items,
        confirmation_subject=get_workplace_setting(
            'registration_confirmation_subject',
            'Workplace Support registration confirmed - {date}',
        ),
        confirmation_message=get_workplace_setting(
            'registration_confirmation_message', DEFAULT_WORKPLACE_CONFIRMATION_MESSAGE
        ),
    )


@app.route('/admin/workplace-support/session/<int:session_id>', methods=['POST'])
@workplace_admin_required
def workplace_admin_update_session(session_id):
    require_csrf()
    workplace_session = WorkplaceSession.query.get_or_404(session_id)
    workplace_session.public_notes = clean_text(request.form.get('public_notes'), 3000) or None
    try:
        workplace_session.max_attendees = max(
            1, min(100, int(request.form.get('max_attendees', 15)))
        )
    except (TypeError, ValueError):
        workplace_session.max_attendees = 15
    workplace_session.is_bookable = request.form.get('is_bookable') == 'on'
    db.session.commit()
    flash('Workplace Support session updated.', 'success')
    return redirect(url_for('workplace_admin', tab='sessions'))


@app.route('/admin/workplace-support/volunteer', methods=['POST'])
@workplace_admin_required
def workplace_admin_add_volunteer():
    require_csrf()
    workplace_session = WorkplaceSession.query.get_or_404(
        request.form.get('workplace_session_id', type=int)
    )
    name = clean_text(request.form.get('volunteer_name'), 200)
    if not name:
        flash('A volunteer name is required.', 'error')
        return redirect(url_for('workplace_admin', tab='rota'))
    role = clean_text(request.form.get('role'), 120)
    if role not in {'Volunteer', 'Mentor'}:
        role = 'Volunteer'
    db.session.add(WorkplaceVolunteer(
        workplace_session_id=workplace_session.id,
        volunteer_name=name,
        volunteer_email=valid_email(request.form.get('volunteer_email')),
        role=role,
        notes=clean_text(request.form.get('notes'), 2000),
    ))
    db.session.commit()
    flash('Volunteer or mentor added to the rota.', 'success')
    return redirect(url_for('workplace_admin', tab='rota'))


@app.route('/admin/workplace-support/volunteer/<int:volunteer_id>/delete', methods=['POST'])
@workplace_admin_required
def workplace_admin_delete_volunteer(volunteer_id):
    require_csrf()
    assignment = WorkplaceVolunteer.query.get_or_404(volunteer_id)
    db.session.delete(assignment)
    db.session.commit()
    flash('Rota assignment removed.', 'success')
    return redirect(url_for('workplace_admin', tab='rota'))


@app.route('/admin/workplace-support/contacts/import', methods=['POST'])
@workplace_admin_required
def workplace_admin_import_contacts():
    require_csrf()
    if request.form.get('permission_confirmed') != 'on':
        flash('Confirm that these contacts may receive AWSS invitations.', 'error')
        return redirect(url_for('workplace_admin', tab='contacts'))
    imported = 0
    reader = csv.reader(io.StringIO(request.form.get('contacts', '')))
    for row in reader:
        if not row:
            continue
        if len(row) == 1:
            name, raw_email = '', row[0]
        else:
            name, raw_email = row[0], row[1]
        email = valid_email(raw_email)
        if email:
            upsert_workplace_contact(
                clean_text(name, 200), email, True, 'Past AWSS attendee import'
            )
            imported += 1
    db.session.commit()
    flash(f'{imported} contact row(s) imported or updated.', 'success')
    return redirect(url_for('workplace_admin', tab='contacts'))


@app.route('/admin/workplace-support/invite', methods=['POST'])
@workplace_admin_required
def workplace_admin_invite_contacts():
    require_csrf()
    workplace_session = WorkplaceSession.query.get_or_404(
        request.form.get('workplace_session_id', type=int)
    )
    if workplace_session.invitation_run:
        flash('The one-off invitation has already been sent for this session.', 'error')
        return redirect(url_for('workplace_admin', tab='contacts'))
    if request.form.get('send_confirmed') != 'on':
        flash('Tick the confirmation box before sending invitations.', 'error')
        return redirect(url_for('workplace_admin', tab='contacts'))

    invitation_run = WorkplaceInvitationRun(
        workplace_session_id=workplace_session.id, sent_count=0, failed_count=0
    )
    db.session.add(invitation_run)
    db.session.commit()

    booking_url = url_for(
        'workplace_book', session_id=workplace_session.id, _external=True
    )
    already_registered = {
        item.email for item in WorkplaceBooking.query.filter_by(
            workplace_session_id=workplace_session.id, cancelled_at=None
        ).all()
    }
    sent = failed = 0
    for contact in WorkplaceContact.query.filter_by(can_invite=True).all():
        if contact.email in already_registered:
            continue
        greeting = f'Hello {escape(contact.name)},' if contact.name else 'Hello,'
        html = f"""<p>{greeting}</p><p>Places are available for the next LAGC
        Autistic Workplace Support Session on
        <strong>{workplace_session.session_date.strftime('%A %d %B %Y')}</strong>,
        1pm–4pm at {WORKPLACE_VENUE_NAME}.</p>
        <p>You can register for one-to-one mentoring, the Speaking Circle, or both.</p>
        <p><a href="{booking_url}">View the session and register</a></p>
        <p>London Autism Group Charity</p>"""
        if send_rich_email(contact.email, 'AWSS - places available', html):
            sent += 1
            contact.last_invited_at = datetime.utcnow()
        else:
            failed += 1
    invitation_run.sent_count = sent
    invitation_run.failed_count = failed
    db.session.commit()
    flash(
        f'Invitations processed: {sent} sent, {failed} failed.',
        'success' if not failed else 'error',
    )
    return redirect(url_for('workplace_admin', tab='contacts'))


@app.route('/admin/workplace-support/email-settings', methods=['POST'])
@workplace_admin_required
def workplace_admin_email_settings():
    require_csrf()
    subject = clean_text(request.form.get('confirmation_subject'), 240)
    message = clean_text(request.form.get('confirmation_message'), 5000)
    if not subject or not message:
        flash('The confirmation subject and message cannot be blank.', 'error')
        return redirect(url_for('workplace_admin', tab='emails'))
    set_workplace_setting('registration_confirmation_subject', subject)
    set_workplace_setting('registration_confirmation_message', message)
    db.session.commit()
    flash('Default Workplace Support confirmation email updated.', 'success')
    return redirect(url_for('workplace_admin', tab='emails'))


@app.route('/admin/workplace-support/session/<int:session_id>/email-message', methods=['POST'])
@workplace_admin_required
def workplace_admin_session_email_message(session_id):
    require_csrf()
    workplace_session = WorkplaceSession.query.get_or_404(session_id)
    workplace_session.confirmation_note = clean_text(
        request.form.get('confirmation_note'), 5000
    ) or None
    db.session.commit()
    flash('Session-specific confirmation note saved.', 'success')
    return redirect(url_for('workplace_admin', tab='emails'))


@app.route('/admin/workplace-support/news', methods=['POST'])
@workplace_admin_required
def workplace_admin_add_news():
    require_csrf()
    headline = clean_text(request.form.get('headline'), 240)
    link = normalise_news_link(request.form.get('link_url'), request.form.get('link_text'))
    if not headline:
        flash('A news headline is required.', 'error')
        return redirect(url_for('workplace_admin', tab='news'))
    if link is None:
        flash('For a news link, provide both valid link URL and link text.', 'error')
        return redirect(url_for('workplace_admin', tab='news'))
    next_order = (
        db.session.query(db.func.max(WorkplaceNewsItem.sort_order)).scalar() or 0
    ) + 1
    db.session.add(WorkplaceNewsItem(
        emoji=clean_text(request.form.get('emoji'), 20),
        headline=headline,
        details=clean_text(request.form.get('details'), 2000),
        link_url=link[0], link_text=link[1], sort_order=next_order,
        is_active=request.form.get('is_active') == 'on',
    ))
    db.session.commit()
    flash('News item added to the AWSS ticker.', 'success')
    return redirect(url_for('workplace_admin', tab='news'))


@app.route('/admin/workplace-support/news/<int:news_id>', methods=['POST'])
@workplace_admin_required
def workplace_admin_update_news(news_id):
    require_csrf()
    item = WorkplaceNewsItem.query.get_or_404(news_id)
    headline = clean_text(request.form.get('headline'), 240)
    link = normalise_news_link(request.form.get('link_url'), request.form.get('link_text'))
    if not headline or link is None:
        flash('Use a headline and complete both link fields if adding a link.', 'error')
        return redirect(url_for('workplace_admin', tab='news'))
    item.emoji = clean_text(request.form.get('emoji'), 20)
    item.headline = headline
    item.details = clean_text(request.form.get('details'), 2000)
    item.link_url, item.link_text = link
    item.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    flash('News item updated.', 'success')
    return redirect(url_for('workplace_admin', tab='news'))


@app.route('/admin/workplace-support/news/<int:news_id>/delete', methods=['POST'])
@workplace_admin_required
def workplace_admin_delete_news(news_id):
    require_csrf()
    db.session.delete(WorkplaceNewsItem.query.get_or_404(news_id))
    db.session.commit()
    flash('News item deleted.', 'success')
    return redirect(url_for('workplace_admin', tab='news'))


@app.route('/admin/workplace-support/news/<int:news_id>/move/<direction>', methods=['POST'])
@workplace_admin_required
def workplace_admin_move_news(news_id, direction):
    require_csrf()
    if direction not in {'up', 'down'}:
        abort(400)
    items = WorkplaceNewsItem.query.order_by(
        WorkplaceNewsItem.sort_order, WorkplaceNewsItem.id
    ).all()
    item = WorkplaceNewsItem.query.get_or_404(news_id)
    index = next((i for i, candidate in enumerate(items) if candidate.id == item.id), None)
    target_index = index - 1 if direction == 'up' else index + 1
    if index is not None and 0 <= target_index < len(items):
        other = items[target_index]
        item.sort_order, other.sort_order = other.sort_order, item.sort_order
        if item.sort_order == other.sort_order:
            item.sort_order, other.sort_order = target_index, index
        db.session.commit()
    return redirect(url_for('workplace_admin', tab='news'))


@app.route('/admin/workplace-support/bookings.csv')
@workplace_admin_required
def workplace_admin_bookings_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Session date', 'Name', 'Email', 'Phone', 'Status', 'Party size',
        'One-to-one mentoring', 'Speaking Circle', 'Attended before',
        'Support hoped for', 'Access or sensory needs', 'Dietary requirements',
        'Additional information', 'Attending with', 'Carer or support worker',
        'Carer organisation', 'Carer mobile', 'Responsibility details',
        'Registered at',
    ])
    bookings = WorkplaceBooking.query.join(WorkplaceSession).order_by(
        WorkplaceSession.session_date
    ).all()
    for item in bookings:
        writer.writerow([
            item.session_ref.session_date.isoformat(), item.full_name, item.email, item.phone,
            'Cancelled' if item.cancelled_at else 'Active', workplace_party_size(item),
            'Yes' if item.attend_mentoring else 'No',
            'Yes' if item.attend_group_discussion else 'No',
            'Yes' if item.attended_before is True else 'No' if item.attended_before is False else '',
            item.support_hoped_for, item.access_needs, item.dietary_requirements,
            item.additional_information, item.companion_details, item.carer_name,
            item.carer_organisation, item.carer_mobile, item.responsibility_details,
            item.created_at.isoformat(),
        ])
    return Response(
        output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=workplace-support-registrations.csv'},
    )

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/dates')
def get_dates():
    """Get all lunch dates"""
    return jsonify(get_all_future_dates())

@app.route('/api/book', methods=['POST'])
def create_booking():
    """Create a new booking"""
    data = request.get_json()
    
    # Validate required fields
    required = ['lunch_date_id', 'first_name', 'last_name', 'email', 
                'is_first_time']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    lunch_date_id = data['lunch_date_id']
    first_name = data['first_name'].strip()
    last_name = data['last_name'].strip()
    email = data['email'].strip().lower()
    main_course = data.get('main_course', '').strip()
    drink = data.get('drink', '').strip()
    is_first_time = data['is_first_time']
    
    # Validate names
    if not first_name or not last_name:
        return jsonify({'error': 'Please enter your full name'}), 400
    
    # Validate email
    if '@' not in email or '.' not in email.split('@')[1]:
        return jsonify({'error': 'Invalid email address'}), 400
    
    # Get lunch date
    lunch_date = LunchDate.query.get(lunch_date_id)
    if not lunch_date:
        return jsonify({'error': 'Lunch date not found'}), 404
    
    # Check if date is bookable
    if not lunch_date.is_bookable:
        return jsonify({'error': 'This date is not currently open for booking'}), 400
    
    # Check if date has passed
    if lunch_date.lunch_date < datetime.now().date():
        return jsonify({'error': 'This lunch date has already passed'}), 400
    
    # Check capacity
    current_bookings = Booking.query.filter(
        Booking.lunch_date_id == lunch_date_id,
        Booking.cancelled_at.is_(None)
    ).count()
    
    if current_bookings >= lunch_date.max_attendees:
        return jsonify({'error': 'This lunch is now fully booked'}), 409
    
    # Check if email already booked this date
    existing_booking = Booking.query.filter(
        Booking.lunch_date_id == lunch_date_id,
        Booking.email == email,
        Booking.cancelled_at.is_(None)
    ).first()
    
    if existing_booking:
        return jsonify({'error': 'You have already booked for this lunch date'}), 409
    
    # Create booking
    cancel_token = secrets.token_urlsafe(32)
    meeting_preference = data.get('meeting_preference', 'church')
    booking = Booking(
        lunch_date_id=lunch_date_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=data.get('phone', '').strip(),
        main_course=main_course,
        drink=drink,
        dietary_requirements=data.get('dietary_requirements', '').strip(),
        meeting_preference=meeting_preference,
        is_first_time=is_first_time,
        additional_info=data.get('additional_info', '').strip(),
        cancel_token=cancel_token
    )
    
    db.session.add(booking)
    db.session.commit()
    
    # Generate confirmation message
    date_display = lunch_date.lunch_date.strftime('%A, %B %d, %Y')
    dietary = data.get('dietary_requirements', '').strip()
    cancel_url = f"{request.host_url.rstrip('/')}/cancel/{cancel_token}"
    
    confirmation_message = generate_confirmation_message(
        name=f"{first_name} {last_name}",
        first_name=first_name,
        date_display=date_display,
        main_course=main_course,
        drink=drink,
        dietary_requirements=dietary,
        cancel_url=cancel_url
    )
    
    # Send confirmation email to user
    send_confirmation_email(
        email,
        f"Booking Confirmed: LAGC Women's Lunch - {date_display}",
        confirmation_message
    )
    
    # Send admin notification
    admin_message = f"""New Women's Lunch Booking:

Name: {first_name} {last_name}
Email: {email}
Phone: {booking.phone or 'Not provided'}
Date: {date_display}

Order:
- Main: {main_course or 'To be decided at the pub'}
- Drink: {drink or 'To be decided at the pub'}
{f"Dietary: {data.get('dietary_requirements', '')}" if data.get('dietary_requirements') else ''}

Meeting Preference: {'Meet at Holy Sepulchre Church at 11:45 AM' if meeting_preference == 'church' else 'Meet at the pub at 12:00 PM'}

First Time: {'Yes' if is_first_time else 'No'}
Additional Info: {data.get('additional_info', 'None')}

View all bookings at: {request.host_url.rstrip('/')}/admin
"""
    
    send_confirmation_email(
        'wg.lagc@gmail.com',
        f"New Women's Lunch Booking: {first_name} {last_name}",
        admin_message
    )
    
    return jsonify({
        'success': True,
        'booking_id': booking.id,
        'confirmation_message': confirmation_message,
        'cancel_token': cancel_token
    })

@app.route('/api/booking/<token>')
def get_booking(token):
    """Get booking details by cancel token"""
    booking = Booking.query.filter_by(cancel_token=token).first()
    
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404
    
    if booking.cancelled_at:
        return jsonify({'error': 'This booking has already been cancelled'}), 410
    
    return jsonify({
        'id': booking.id,
        'first_name': booking.first_name,
        'last_name': booking.last_name,
        'email': booking.email,
        'date': booking.lunch_date_ref.lunch_date.isoformat(),
        'date_display': booking.lunch_date_ref.lunch_date.strftime('%A, %B %d, %Y'),
        'main_course': booking.main_course,
        'drink': booking.drink,
        'dietary_requirements': booking.dietary_requirements,
        'is_first_time': booking.is_first_time
    })

@app.route('/api/cancel/<token>', methods=['POST'])
def cancel_booking(token):
    """Cancel a booking"""
    booking = Booking.query.filter_by(cancel_token=token).first()
    
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404
    
    if booking.cancelled_at:
        return jsonify({'error': 'This booking has already been cancelled'}), 410
    
    # Store booking info before cancelling (for email notification)
    date_display = booking.lunch_date_ref.lunch_date.strftime('%A, %B %d, %Y')
    first_name = booking.first_name
    last_name = booking.last_name
    email = booking.email
    phone = booking.phone or 'Not provided'
    main_course = booking.main_course or 'Not specified'
    drink = booking.drink or 'Not specified'
    dietary = booking.dietary_requirements or 'None'
    meeting_pref = booking.meeting_preference or 'church'
    
    booking.cancelled_at = datetime.utcnow()
    db.session.commit()
    
    # Send admin notification about cancellation
    cancel_message = f"""❌ Booking Cancelled:

Name: {first_name} {last_name}
Email: {email}
Phone: {phone}
Date: {date_display}

Original Order:
- Main: {main_course}
- Drink: {drink}
- Dietary: {dietary}

Meeting Preference: {'Meet at Holy Sepulchre Church at 11:45 AM' if meeting_pref == 'church' else 'Meet at the pub at 12:00 PM'}

This booking has been cancelled by the user.

View all bookings at: {request.host_url.rstrip('/')}/admin
"""
    
    send_confirmation_email(
        'wg.lagc@gmail.com',
        f"Cancelled Booking: {first_name} {last_name} - {date_display}",
        cancel_message
    )
    
    return jsonify({
        'success': True,
        'message': 'Your booking has been cancelled successfully'
    })

@app.route('/api/my-bookings', methods=['POST'])
def get_my_bookings():
    """Get all bookings for an email address"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        today = datetime.now().date()
        
        # Get all bookings for this email that are not cancelled
        bookings = Booking.query.filter(
            Booking.email == email,
            Booking.cancelled_at.is_(None)
        ).all()
        
        result = []
        for booking in bookings:
            # Only include future bookings
            if booking.lunch_date_ref and booking.lunch_date_ref.lunch_date >= today:
                result.append({
                    'id': booking.id,
                    'date': booking.lunch_date_ref.lunch_date.isoformat(),
                    'date_display': booking.lunch_date_ref.lunch_date.strftime('%A, %B %d, %Y'),
                    'main_course': booking.main_course,
                    'drink': booking.drink,
                    'cancel_token': booking.cancel_token
                })
        
        # Sort by date
        result.sort(key=lambda x: x['date'])
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in get_my_bookings: {e}")
        return jsonify({'error': 'Server error occurred'}), 500

# ============================================================================
# ADMIN API ENDPOINTS
# ============================================================================

@app.route('/api/admin/dates')
@admin_required
def admin_get_dates():
    """Get all lunch dates for admin"""
    dates = LunchDate.query.order_by(LunchDate.lunch_date).all()
    
    result = []
    for ld in dates:
        current_bookings = Booking.query.filter(
            Booking.lunch_date_id == ld.id,
            Booking.cancelled_at.is_(None)
        ).count()
        
        result.append({
            'id': ld.id,
            'date': ld.lunch_date.isoformat(),
            'display': ld.lunch_date.strftime('%A, %B %d, %Y'),
            'is_bookable': ld.is_bookable,
            'max_attendees': ld.max_attendees,
            'bookings_count': current_bookings,
            'spots_left': ld.max_attendees - current_bookings
        })
    
    return jsonify(result)

@app.route('/api/admin/dates/<int:date_id>', methods=['PUT'])
@admin_required
def admin_update_date(date_id):
    """Update lunch date (toggle bookable status)"""
    require_csrf()
    lunch_date = LunchDate.query.get_or_404(date_id)
    data = request.get_json()
    
    if 'is_bookable' in data:
        lunch_date.is_bookable = data['is_bookable']
    
    db.session.commit()
    
    return jsonify({
        'id': lunch_date.id,
        'is_bookable': lunch_date.is_bookable
    })

@app.route('/api/admin/bookings')
@admin_required
def admin_get_bookings():
    """Get all upcoming bookings"""
    bookings = Booking.query.join(LunchDate).filter(
        Booking.cancelled_at.is_(None),
        LunchDate.lunch_date >= datetime.now().date()
    ).order_by(LunchDate.lunch_date).all()
    
    result = []
    for booking in bookings:
        result.append({
            'id': booking.id,
            'first_name': booking.first_name,
            'last_name': booking.last_name,
            'email': booking.email,
            'phone': booking.phone,
            'date': booking.lunch_date_ref.lunch_date.isoformat(),
            'date_display': booking.lunch_date_ref.lunch_date.strftime('%A, %B %d, %Y'),
            'main_course': booking.main_course,
            'drink': booking.drink,
            'dietary_requirements': booking.dietary_requirements,
            'meeting_preference': booking.meeting_preference,
            'is_first_time': booking.is_first_time,
            'additional_info': booking.additional_info
        })
    
    return jsonify(result)

@app.route('/api/admin/bookings/archive')
@admin_required
def admin_get_bookings_archive():
    """Get all past bookings (archived)"""
    bookings = Booking.query.join(LunchDate).filter(
        Booking.cancelled_at.is_(None),
        LunchDate.lunch_date < datetime.now().date()
    ).order_by(LunchDate.lunch_date.desc()).all()
    
    result = []
    for booking in bookings:
        result.append({
            'id': booking.id,
            'first_name': booking.first_name,
            'last_name': booking.last_name,
            'email': booking.email,
            'phone': booking.phone,
            'date': booking.lunch_date_ref.lunch_date.isoformat(),
            'date_display': booking.lunch_date_ref.lunch_date.strftime('%A, %B %d, %Y'),
            'main_course': booking.main_course,
            'drink': booking.drink,
            'dietary_requirements': booking.dietary_requirements,
            'meeting_preference': booking.meeting_preference,
            'is_first_time': booking.is_first_time,
            'additional_info': booking.additional_info
        })
    
    return jsonify(result)

@app.route('/api/admin/settings')
@admin_required
def admin_get_settings():
    """Get settings"""
    return jsonify({
        'confirmation_message': get_setting('confirmation_message', get_default_confirmation_message())
    })

@app.route('/api/admin/settings', methods=['POST'])
@admin_required
def admin_update_settings():
    """Update settings"""
    require_csrf()
    data = request.get_json()
    
    if 'confirmation_message' in data:
        set_setting('confirmation_message', data['confirmation_message'])
    
    return jsonify({'success': True})

@app.route('/api/admin/bookings/<int:booking_id>', methods=['DELETE'])
@admin_required
def admin_delete_booking(booking_id):
    """Delete a booking completely (not just cancel)"""
    require_csrf()
    booking = Booking.query.get_or_404(booking_id)
    
    # Permanently delete the booking
    db.session.delete(booking)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Booking deleted permanently'})

# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_default_data()
    app.run(debug=True, host='0.0.0.0', port=5002)
