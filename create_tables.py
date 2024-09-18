# create_tables.py
from app import app, db  # Replace 'your_application' with the filename of your Flask app

with app.app_context():
    db.create_all()
    print("Database tables created.")
