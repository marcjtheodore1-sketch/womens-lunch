import sys
import os

# Add the project directory to the path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

# Import and initialise the Flask app. ``create_all`` only adds missing tables,
# so the existing Women's Lunch data remains untouched.
from app import app as application, db, init_default_data

with application.app_context():
    db.create_all()
    init_default_data()
