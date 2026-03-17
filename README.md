# LAGC Autistic Women's Lunch Group Registration System

A registration system for the London Autism Group Charity's monthly Autistic Women's Lunch Group.

## Features

- **Monthly Lunch Bookings**: Max 12 attendees per lunch
- **Menu Selection**: Attendees choose their meal and drink when booking
- **Budget**: £20 per person (main + non-alcoholic drink)
- **Venue**: Cittie of Yorke, Holborn
- **Booking Window**: Only the next upcoming lunch is bookable
- **Admin Panel**: Manage dates, view bookings, archive past events
- **Email Notifications**: Automatic confirmation emails

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

The app will be available at http://localhost:5002

## Admin Access

- URL: `/admin`
- Default password: `womenslunch`

## Environment Variables

- `ADMIN_PASSWORD`: Admin login password
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: Email configuration
- `ENABLE_EMAIL`: Set to `true` to enable email sending

## Deployment

Deploy to PythonAnywhere or similar hosting service. Use the included `wsgi.py` for WSGI configuration.
