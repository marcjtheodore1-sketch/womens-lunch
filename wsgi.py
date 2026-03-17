import sys
import os

# Add the project directory to the path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

# Email configuration
os.environ['ENABLE_EMAIL'] = 'true'
os.environ['SMTP_HOST'] = 'smtp.gmail.com'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USER'] = 'wg.lagc@gmail.com'
os.environ['SMTP_PASSWORD'] = 'hqeqxqzaecqopdyt'
os.environ['SMTP_FROM'] = 'wg.lagc@gmail.com'

# Import the Flask app
from app import app as application
