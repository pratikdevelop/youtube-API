from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

# Initialize the SQLAlchemy object
db = SQLAlchemy()

# Define Video model for database
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_url = db.Column(db.String(500), nullable=False)
    segment_length = db.Column(db.Integer, nullable=False)
    file_urls = db.Column(db.Text, nullable=False)  # JSON list of file URLs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, video_url, segment_length, file_urls):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls

    def to_dict(self):
        """Helper method to convert Video object to dictionary"""
        return {
            'id': self.id,
            'video_url': self.video_url,
            'segment_length': self.segment_length,
            'file_urls': json.loads(self.file_urls),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

# Helper method to create tables, if they don't exist
def create_db(app):
    with app.app_context():
        db.create_all()
