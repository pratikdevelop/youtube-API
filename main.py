import os
import uuid
import logging
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import yt_dlp as youtube_dl
import boto3
from botocore.exceptions import NoCredentialsError
from models import db, Video, create_db

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
class Config:
    UPLOAD_FOLDER = 'uploads'
    COOKIE_FILE = os.getenv('COOKIE_FILE')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI')
    AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')
    AWS_S3_REGION = os.getenv('AWS_S3_REGION')
    AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
    AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')

# Validate required environment variables
required_env_vars = ['DATABASE_URI', 'AWS_S3_BUCKET', 'AWS_S3_REGION', 'AWS_ACCESS_KEY', 'AWS_SECRET_KEY']
for var in required_env_vars:
    if not os.getenv(var):
        logging.error(f"Missing required environment variable: {var}")
        raise EnvironmentError(f"Missing required environment variable: {var}")

app.config.from_object(Config)

# Initialize the database
db.init_app(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=Config.AWS_ACCESS_KEY,
    aws_secret_access_key=Config.AWS_SECRET_KEY,
    region_name=Config.AWS_S3_REGION
)

# Create database tables
create_db(app)

@app.route('/')
def index():
    return render_template('index.html')

def download_social_video(video_url, output_path):
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4',
        'cookiefile': Config.COOKIE_FILE,
        'verbose': True,
    }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        logging.error(f"Error downloading video from {video_url}: {e}")
        raise

def upload_to_s3(file_path, file_name):
    try:
        s3_client.upload_file(file_path, Config.AWS_S3_BUCKET, file_name)
        return f"https://{Config.AWS_S3_BUCKET}.s3.{Config.AWS_S3_REGION}.amazonaws.com/{file_name}"
    except NoCredentialsError:
        logging.error("AWS credentials not available.")
        return None
    except Exception as e:
        logging.error(f"Error uploading {file_name} to S3: {e}")
        return None

def download_and_upload_social_video(video_url):
    video_file = os.path.join(app.config['UPLOAD_FOLDER'], f"social_{uuid.uuid4().hex}.mp4")
    try:
        download_social_video(video_url, video_file)
        s3_url = upload_to_s3(video_file, os.path.basename(video_file))
        return {'videoUrl': s3_url} if s3_url else {'error': 'Failed to upload video'}
    except Exception as e:
        return {'error': 'Error downloading video', 'details': str(e)}
    finally:
        if os.path.exists(video_file):
            os.remove(video_file)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    video_url = data.get('url')

    if not video_url:
        return jsonify({'error': 'Missing video URL.'}), 400

    result = download_and_upload_social_video(video_url)
    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)

@app.route('/list-videos', methods=['GET'])
def list_videos():
    videos = Video.query.all()
    video_list = [video.to_dict() for video in videos]
    return jsonify(video_list)

if __name__ == '__main__':
    app.run(debug=True)