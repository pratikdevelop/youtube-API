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
from botocore.exceptions import NoCredentialsError

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
COOKIE_FILE = os.getenv('COOKIE_FILE')  # YouTube cookies file path
DATABASE_URI = os.getenv('DATABASE_URI')  # Database connection URI
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')  # AWS S3 bucket name
AWS_S3_REGION = os.getenv('AWS_S3_REGION')  # AWS S3 region
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')  # AWS access key
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')  # AWS secret key

# Flask configurations
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize the database
db = SQLAlchemy(app)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_S3_REGION
)

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

# Create database tables
with app.app_context():
    db.create_all()

# Helper function to download a YouTube video
def download_video_file(video_url, output_path):
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4',
        'cookiefile': COOKIE_FILE,  # Use YouTube cookies
        'verbose': True,
    }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        raise

# Helper function to upload a file to AWS S3
def upload_to_s3(file_path, file_name):
    try:
        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        file_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{file_name}"
        return file_url
    except NoCredentialsError:
        logging.error("AWS credentials not available.")
        return None
    except Exception as e:
        logging.error(f"Error uploading to S3: {e}")
        return None

# Helper function to process a video
def process_video_task(video_url, segment_length):
    video_file = os.path.join(UPLOAD_FOLDER, f"video_{uuid.uuid4().hex}.mp4")
    time.sleep(random.uniform(1, 3))  # Simulate delay

    try:
        download_video_file(video_url, video_file)
    except Exception as e:
        return {'error': 'Error downloading video', 'details': str(e)}

    # Probe video duration
    try:
        probe = ffmpeg.probe(video_file, v='error', select_streams='v:0', show_entries='stream=duration')
        duration = float(probe['streams'][0]['duration'])
    except ffmpeg.Error as e:
        return {'error': 'Error probing video duration', 'details': str(e)}

    file_urls = []
    for start_time in range(0, int(duration), segment_length):
        short_file = os.path.join(UPLOAD_FOLDER, f"short_{uuid.uuid4().hex}.mp4")
        try:
            ffmpeg.input(video_file, ss=start_time, t=segment_length).output(short_file).run(overwrite_output=True)
            s3_url = upload_to_s3(short_file, os.path.basename(short_file))
            if s3_url:
                file_urls.append(s3_url)
        except ffmpeg.Error as e:
            logging.error(f"Error processing video segment: {e}")
            return {'error': 'Error processing video segment', 'details': str(e)}

    os.remove(video_file)
    video_record = Video(video_url=video_url, segment_length=segment_length, file_urls=json.dumps(file_urls))
    db.session.add(video_record)
    db.session.commit()
    return {'fileUrls': file_urls}

# Endpoint to process video
@app.route('/process-video', methods=['POST'])
def process_video():
    data = request.json
    video_url = data.get('url')
    segment_length = data.get('segment_length', 60)

    if not video_url:
        return jsonify({'error': 'Missing video URL.'}), 400

    try:
        segment_length = int(segment_length)
        if segment_length <= 0:
            raise ValueError("Segment length must be positive.")
    except ValueError as e:
        return jsonify({'error': 'Invalid segment length.', 'details': str(e)}), 400

    result = process_video_task(video_url, segment_length)
    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)

# Endpoint to list processed videos
@app.route('/list-videos', methods=['GET'])
def list_videos():
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
