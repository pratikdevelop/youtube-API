from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import uuid
import json
import yt_dlp as youtube_dl
import logging
import random
import time
import boto3
from botocore.exceptions import NoCredentialsError
from flask_pymongo import PyMongo

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
mongo = PyMongo(app)

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_S3_REGION
)

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
    video_data = {
        'platform': 'instagram',
        'video_url': result['videoUrl'],
        'file_urls': [result['videoUrl']],
        'created_at': time.time()
    }
    mongo.db.videos.insert_one(video_data)  # Save to MongoDB collection 'videos'

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
    video_data = {
        'platform': 'facebook',
        'video_url': result['videoUrl'],
        'file_urls': [result['videoUrl']],
        'created_at': time.time()
    }
    mongo.db.videos.insert_one(video_data)  # Save to MongoDB collection 'videos'

    return jsonify(result)

# Endpoint to list processed videos
@app.route('/list-videos', methods=['GET'])
def list_videos():
    videos = mongo.db.videos.find()  # Fetch all videos from MongoDB
    video_list = []
    for video in videos:
        video_list.append({
            'platform': video['platform'],
            'video_url': video['video_url'],
            'file_urls': video['file_urls'],
            'created_at': video['created_at']
        })
    return jsonify(video_list)

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
    app.run(debug=True)
