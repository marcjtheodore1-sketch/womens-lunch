"""
LAGC Autistic Women's Lunch Group Registration System
Monthly lunch at Cittie of Yorke - max 12 attendees, £20 per person
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import secrets
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lunch_bookings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration - HARDCODED for production
app.config['SMTP_HOST'] = 'smtp.gmail.com'
app.config['SMTP_PORT'] = 587
app.config['SMTP_USER'] = 'wg.lagc@gmail.com'
app.config['SMTP_PASSWORD'] = 'hqeqxqzaecqopdyt'
app.config['SMTP_FROM'] = 'wg.lagc@gmail.com'
app.config['ENABLE_EMAIL'] = True

# Admin password
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'womenslunch')

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
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

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
    """Landing page"""
    return render_template('landing.html')

@app.route('/book')
def book():
    """Booking page"""
    return render_template('book.html')

@app.route('/admin')
def admin():
    """Admin page"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
            error = 'Invalid password'
    
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('landing'))

@app.route('/cancel/<token>')
def cancel_page(token):
    """Cancellation page"""
    return render_template('cancel.html', token=token)

@app.route('/access')
def access_gate():
    """Access code gate page"""
    return render_template('access.html')

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
    data = request.get_json()
    
    if 'confirmation_message' in data:
        set_setting('confirmation_message', data['confirmation_message'])
    
    return jsonify({'success': True})

@app.route('/api/admin/bookings/<int:booking_id>', methods=['DELETE'])
@admin_required
def admin_delete_booking(booking_id):
    """Delete a booking completely (not just cancel)"""
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
