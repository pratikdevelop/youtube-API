from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy
db = SQLAlchemy()

# Define the Video model
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_url = db.Column(db.String(500), nullable=False)
    segment_length = db.Column(db.Integer, nullable=False)
    file_urls = db.Column(db.Text, nullable=False)  # Store multiple URLs as JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, video_url, segment_length, file_urls):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls
