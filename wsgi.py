import sys
import os

# Add the project directory to the path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

# Email configuration - MUST be set BEFORE importing Flask app
os.environ['ENABLE_EMAIL'] = 'true'
os.environ['SMTP_HOST'] = 'smtp.gmail.com'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USER'] = 'wg.lagc@gmail.com'
os.environ['SMTP_PASSWORD'] = 'hqeqxqzaecqopdyt'
os.environ['SMTP_FROM'] = 'wg.lagc@gmail.com'

# Debug - verify environment variables are set
print(f"[WSGI] ENABLE_EMAIL set to: {os.environ.get('ENABLE_EMAIL')}")
print(f"[WSGI] SMTP_USER set to: {os.environ.get('SMTP_USER')}")

# Import the Flask app
from app import app as application

# Verify Flask config received the values
print(f"[WSGI] Flask ENABLE_EMAIL: {application.config.get('ENABLE_EMAIL')}")
print(f"[WSGI] Flask SMTP_USER: {application.config.get('SMTP_USER')}")
