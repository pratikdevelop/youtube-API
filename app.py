from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
import yt_dlp as youtube_dl
import logging
import uuid
from flask_pymongo import PyMongo
from datetime import datetime
import boto3
from botocore.exceptions import NoCredentialsError
from moviepy.editor import VideoFileClip


# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
COOKIE_FILE = os.getenv('COOKIE_FILE')  # Optional: Cookies file for authenticated requests
MONGO_URI = os.getenv('MONGO_URI')  # MongoDB connection URI
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')  # AWS S3 bucket name
AWS_S3_REGION = os.getenv('AWS_S3_REGION')  # AWS S3 region
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')  # AWS access key
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')  # AWS secret key

# Flask configurations
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MONGO_URI'] = MONGO_URI

# Initialize PyMongo (MongoDB client)
mongo = None

# Define Video model for MongoDB
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

# Helper method to initialize MongoDB client (replace 'db' with 'mongo')
def create_db(app):
    global mongo
    mongo = PyMongo(app)  # Initialize PyMongo with the app
    # Ensure the video collection is available in MongoDB
    mongo.db.videos.create_index([('video_url', 1)], unique=True)

# Helper method to add a video to the MongoDB
def save_video(video_url, segment_length, file_urls):
    video = Video(video_url, segment_length, file_urls)
    video_data = video.to_dict()

    # Insert the video data into the MongoDB 'videos' collection
    try:
        mongo.db.videos.insert_one(video_data)
    except Exception as e:
        # Handle insertion failure
        print(f"Error inserting video: {str(e)}")
        return None

    return video_data

# Helper method to list all processed videos from MongoDB
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
   
with app.app_context():
    def before_request():
        create_db(app)
    
@app.route('/')
def index():
    return render_template('index.html')

# Helper function to download a video from a URL (YouTube, Instagram, Facebook)
def download_social_video(video_url, output_path):
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4',
        'cookiefile': COOKIE_FILE,  # Optional: Use cookies for authenticated downloads
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

# Helper function to download and upload a video from Instagram or Facebook
def download_and_upload_social_video(video_url):
    video_file = os.path.join(UPLOAD_FOLDER, f"social_{uuid.uuid4().hex}.mp4")
    try:
        download_social_video(video_url, video_file)
        s3_url = upload_to_s3(video_file, os.path.basename(video_file))
        return {'videoUrl': s3_url} if s3_url else {'error': 'Failed to upload video'}
    except Exception as e:
        return {'error': 'Error downloading video', 'details': str(e)}
    finally:
        if os.path.exists(video_file):
            os.remove(video_file)

@app.route('/process-video', methods=['POST'])
def download_youtube():
    data = request.json
    video_url = data.get('url')
    segment_length= data.get('segment_length')

    video_file = f"uploads/{uuid.uuid4().hex}.mp4"

    # Download video using yt-dlp
    ydl_opts = {
        'outtmpl': video_file,
        'format': 'mp4',
        'quiet': True,
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        # Process the video: split into segments of the specified length
        video_clip = VideoFileClip(video_file)
        video_duration = video_clip.duration  # in seconds
        segment_urls = []

        # Split the video into segments
        for start_time in range(0, int(video_duration), int(segment_length)):
            end_time = min(start_time + int(segment_length), video_duration)
            segment_file = f"uploads/{uuid.uuid4().hex}_segment.mp4"
            segment_clip = video_clip.subclip(start_time, end_time)
            segment_clip.write_videofile(segment_file, codec='libx264', audio_codec='aac')

            # Upload each segment to AWS S3
            s3_url = upload_to_s3(segment_file, os.path.basename(segment_file))
            segment_urls.append(s3_url)

            # Remove local segment file after uploading
            if os.path.exists(segment_file):
                os.remove(segment_file)

        # Remove the original video file
        if os.path.exists(video_file):
            os.remove(video_file)

        return {'videoUrl': segment_urls}

    except Exception as e:
        logging.error(f"Error downloading or processing video: {e}")
        return {'error': 'Failed to download or process video', 'details': str(e)}

# Endpoint to download Instagram stories, reels, or posts
@app.route('/download-instagram', methods=['POST'])
def download_instagram():
    data = request.json
    video_url = data.get('url')

    if not video_url:
        return jsonify({'error': 'Missing video URL.'}), 400

    result = download_and_upload_social_video(video_url)
    if 'error' in result:
        return jsonify(result), 500

    # Save to MongoDB
    video_data = save_video(result['videoUrl'], segment_length=0, file_urls=[result['videoUrl']])  # Adjust segment length and file URLs
    if not video_data:
        return jsonify({'error': 'Failed to save video to database'}), 500

    return jsonify(result)

# Endpoint to download Facebook stories, reels, or posts
@app.route('/download-facebook', methods=['POST'])
def download_facebook():
    data = request.json
    video_url = data.get('url')

    if not video_url:
        return jsonify({'error': 'Missing video URL.'}), 400

    result = download_and_upload_social_video(video_url)
    if 'error' in result:
        return jsonify(result), 500

    # Save to MongoDB
    video_data = save_video(result['videoUrl'], segment_length=0, file_urls=[result['videoUrl']])  # Adjust segment length and file URLs
    if not video_data:
        return jsonify({'error': 'Failed to save video to database'}), 500

    return jsonify(result)

# Endpoint to list processed videos
@app.route('/list-videos', methods=['GET'])
def list_videos_route():
    videos = get_all_videos()  # Fetch all videos from MongoDB
    return jsonify(videos)

@app.route('/get-presigned-url', methods=['GET'])
def get_presigned_url():
    file_key = request.args.get('file_key')  # Example: short_795af7cb9456400abbc9f1bad5c2b11d.mp4

    try:
        # Generate a pre-signed URL valid for 1 hour
        url = s3_client.generate_presigned_url('get_object',
                                        Params={'Bucket': os.getenv('AWS_S3_BUCKET'), 'Key': file_key},
                                        ExpiresIn=3600)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    create_db(app)

    app.run(debug=True)
