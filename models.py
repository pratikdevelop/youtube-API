# database.py

from flask_pymongo import PyMongo
from datetime import datetime
import json
import logging

# Initialize PyMongo (MongoDB client)
mongo = None

def init_db(app):
    global mongo
    mongo = PyMongo(app)  # Initialize PyMongo with the app
    # Ensure the video collection is available in MongoDB
    mongo.db.videos.create_index([('video_url', 1)], unique=True)

class Video:
    def __init__(self, video_url, segment_length, file_urls):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls  # This will be a JSON list of file URLs
        self.created_at = datetime.utcnow()

    def to_dict(self):
        """Helper method to convert Video object to dictionary"""
        return {
            'video_url': self.video_url,
            'segment_length': self.segment_length,
            'file_urls': json.loads(self.file_urls) if isinstance(self.file_urls, str) else self.file_urls,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

def save_video(video_url, segment_length, file_urls):
    video = Video(video_url, segment_length, file_urls)
    video_data = video.to_dict()

    # Insert the video data into the MongoDB 'videos' collection
    try:
        mongo.db.videos.insert_one(video_data)
    except Exception as e:
        # Handle insertion failure
        logging.error(f"Error inserting video: {str(e)}")
        return None

    return video_data

def get_all_videos():
    videos = mongo.db.videos.find()
    video_list = []
    for video in videos:
        video_list.append({
            'video_url': video['video_url'],
            'segment_length': video['segment_length'],
            'file_urls': video['file_urls'],
            'created_at': video['created_at']
        })
    return video_list

