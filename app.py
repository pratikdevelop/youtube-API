from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
import json
import yt_dlp as youtube_dl
import ffmpeg
import logging
import random
import time
from datetime import datetime
from dotenv import load_dotenv

import boto3

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
COOKIE_FILE = os.getenv('COOKIE_FILE')  # Load from environment variable
DATABASE_URI = os.getenv('DATABASE_URI')  # Load from environment variable

# AWS S3 Configuration from environment variables
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')
AWS_S3_REGION = os.getenv('AWS_S3_REGION')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')

# Flask Configurations
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize the database
db = SQLAlchemy(app)

# Initialize S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_S3_REGION
)

# Define the Video model
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_url = db.Column(db.String(500), nullable=False)
    segment_length = db.Column(db.Integer, nullable=False)
    file_urls = db.Column(db.Text, nullable=False)  # Store URLs as JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, video_url, segment_length, file_urls):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls

# Create the database tables
with app.app_context():
    db.create_all()

# Helper function to download a video
def download_video_file(video_url, output_path):
    """
    Downloads a video from YouTube using yt-dlp with cookies for authentication.
    """
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4',
        'cookiefile': COOKIE_FILE,  # Use cookies for restricted videos
        'verbose': True,  # Enable verbose logging for debugging
    }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        raise

# Helper function to upload video to S3
def upload_to_s3(file_path, file_name):
    """
    Uploads a file to S3 and returns the file's URL.
    """
    try:
        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        file_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{file_name}"
        return file_url
    except NoCredentialsError:
        logging.error("AWS credentials not available")
        return None
    except Exception as e:
        logging.error(f"Error uploading file to S3: {e}")
        return None

# Helper function to process video
def process_video_task(video_url, segment_length):
    """
    Downloads and splits a video into smaller segments of the specified length.
    """
    video_file = os.path.join(UPLOAD_FOLDER, f"video_{uuid.uuid4().hex}.mp4")

    # Add a random delay to simulate processing time
    time.sleep(random.uniform(1, 3))

    try:
        download_video_file(video_url, video_file)
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return {'error': 'Error downloading video', 'details': str(e)}

    # Probe video duration
    try:
        probe = ffmpeg.probe(video_file, v='error', select_streams='v:0', show_entries='stream=duration')
        duration = float(probe['streams'][0]['duration'])
    except ffmpeg.Error as e:
        logging.error(f"Error probing video duration: {e}")
        return {'error': 'Error probing video duration', 'details': str(e)}

    file_urls = []
    for start_time in range(0, int(duration), segment_length):
        end_time = min(start_time + segment_length, duration)
        short_file = os.path.join(UPLOAD_FOLDER, f"short_{uuid.uuid4().hex}.mp4")
        try:
            ffmpeg.input(video_file, ss=start_time, to=end_time).output(short_file).run(overwrite_output=True)

            # Upload to S3
            s3_url = upload_to_s3(short_file, os.path.basename(short_file))
            if s3_url:
                file_urls.append(s3_url)
            else:
                logging.error("Failed to upload segment to S3")
        except ffmpeg.Error as e:
            logging.error(f"Error processing video segment: {e}")
            return {'error': 'Error processing video segment', 'details': str(e)}

    os.remove(video_file)  # Clean up the original video file

    # Save metadata in the database
    video_record = Video(video_url=video_url, segment_length=segment_length, file_urls=json.dumps(file_urls))
    db.session.add(video_record)
    db.session.commit()

    return {'fileUrls': file_urls}

# API endpoint to process a video
@app.route('/process-video', methods=['POST'])
def process_video():
    """
    Endpoint to process a video URL into smaller segments and upload to S3.
    """
    data = request.json
    video_url = data.get('url')
    segment_length = data.get('segment_length', 60)  # Default to 60 seconds if not provided

    # Validate segment_length
    try:
        segment_length = int(segment_length)
        if segment_length <= 0:
            raise ValueError("Segment length must be a positive integer.")
    except (ValueError, TypeError) as e:
        logging.error(f"Invalid segment length: {e}")
        return jsonify({'error': 'Invalid segment length', 'details': str(e)}), 400

    # Start video processing task
    result = process_video_task(video_url, segment_length)
    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)

# API endpoint to download a processed video file
@app.route('/download/<filename>')
def download_file(filename):
    """
    Endpoint to download a processed video file.
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True, mimetype='video/mp4')

# API endpoint to list all processed videos
@app.route('/list-videos', methods=['GET'])
def list_videos():
    """
    Endpoint to list all processed videos.
    """
    videos = Video.query.all()
    video_list = [
        {
            'id': video.id,
            'video_url': video.video_url,
            'segment_length': video.segment_length,
            'file_urls': json.loads(video.file_urls),
            'created_at': video.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        for video in videos
    ]
    return jsonify(video_list)

if __name__ == '__main__':
    app.run(debug=True)
