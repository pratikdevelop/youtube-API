from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
import yt_dlp as youtube_dl
import logging
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
import subprocess
from models import mongo, init_db, save_video, get_all_videos  # Import database functions

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
COOKIE_FILE = os.getenv('COOKIE_FILE')  # Path to cookies file for authenticated requests
MONGO_URI = os.getenv('MONGO_URI')  # MongoDB connection URI
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')  # AWS S3 bucket name
AWS_S3_REGION = os.getenv('AWS_S3_REGION')  # AWS S3 region
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')  # AWS access key
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')  # AWS secret key

# Flask configurations
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MONGO_URI'] = MONGO_URI
if (mongo == none): 
    print('===========================gjkfjgkf')
    init_db(app)

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

# Helper function to download a video from YouTube or other social media platforms
def download_social_video(video_url, output_path):
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'mp4',
        'quiet': False,
        'verbose': True,
    }

    # Use cookies for authentication if COOKIE_FILE is provided
    cookies_path = os.path.join(os.getcwd(), 'cookies.txt')  # Assumes cookies.txt is in the root folder
    if COOKIE_FILE:
        ydl_opts['cookies'] = cookies_path
    else:
        # Fallback to using cookies from the browser
        ydl_opts['cookiesfrombrowser'] = ('chrome',)

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except youtube_dl.utils.DownloadError as e:
        logging.error(f"Error downloading video: {e}")
        raise
    except Exception as e:
        logging.error(f"General error downloading video: {e}")
        raise

# Helper function to upload a file to AWS S3
def upload_to_s3(file_path, file_name):
    s3_client = boto3.client('s3',
                             region_name=AWS_S3_REGION,
                             aws_access_key_id=AWS_ACCESS_KEY,
                             aws_secret_access_key=AWS_SECRET_KEY)
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

# Helper function to get the duration of a video file using ffprobe
def get_video_duration(video_file):
    command = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_file
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

@app.route('/process-video', methods=['POST'])
def download_youtube():
    data = request.json
    video_url = data.get('url')
    segment_length = data.get('segment_length')

    if not video_url or not segment_length:
        return jsonify({'error': 'Missing video URL or segment length.'}), 400

    video_file = f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}.mp4"

    # Download video using yt-dlp
    try:
        download_social_video(video_url, video_file)

        # Check if the file was downloaded
        if not os.path.exists(video_file):
            return jsonify({'error': 'Failed to download video.'}), 500

        # Use ffmpeg to split the video into segments
        video_duration = get_video_duration(video_file)
        segment_urls = []

        for start_time in range(0, int(video_duration), int(segment_length)):
            end_time = min(start_time + int(segment_length), video_duration)
            segment_file = f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}_segment.mp4"

            # Use ffmpeg to create the segment
            command = [
                'ffmpeg',
                '-i', video_file,
                '-ss', str(start_time),
                '-to', str(end_time),
                '-c', 'copy',  # Copy codec
                segment_file
            ]
            subprocess.run(command, check=True)

            # Upload each segment to AWS S3
            s3_url = upload_to_s3(segment_file, os.path.basename(segment_file))

            if s3_url:
                segment_urls.append(s3_url)
            else:
                logging.error(f"Failed to upload segment: {segment_file}")

            # Remove local segment file after uploading
            if os.path.exists(segment_file):
                os.remove(segment_file)

        # Remove the original video file
        if os.path.exists(video_file):
            os.remove(video_file)

        # Save video metadata to MongoDB
        video_data = save_video(video_url, segment_length=segment_length, file_urls=segment_urls)

        return jsonify({'videoUrl': segment_urls})

    except youtube_dl.utils.DownloadError as e:
        logging.error(f"Download error: {e}")
        return jsonify({'error': 'Failed to download video', 'details': str(e)}), 500

    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg error: {e}")
        return jsonify({'error': 'Failed to process video segments', 'details': str(e)}), 500

    except Exception as e:
        logging.error(f"General error: {e}")
        return jsonify({'error': 'Failed to download or process video', 'details': str(e)}), 500
    

# New Endpoint: Download Instagram reel or video
@app.route('/download-instagram', methods=['POST'])
def download_instagram():
    data = request.json
    post_url = data.get('url')

    if not post_url:
        return jsonify({'error': 'Missing Instagram post URL.'}), 400

    try:
        # Use instaloader to download the video
        instaloader_instance = instaloader.Instaloader()
        
        # Temporary folder to save the file
        download_folder = os.path.join(UPLOAD_FOLDER, "instagram")
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)
        
        # Download the video or reel
        instaloader_instance.download_post(
            instaloader.Post.from_shortcode(instaloader_instance.context, post_url.split("/")[-2]),
            target=download_folder
        )
        
        # Find the downloaded video file
        downloaded_files = os.listdir(download_folder)
        video_file = next((file for file in downloaded_files if file.endswith('.mp4')), None)
        
        if not video_file:
            return jsonify({'error': 'Failed to download video.'}), 500

        video_path = os.path.join(download_folder, video_file)
        
        # Upload the video to S3
        s3_url = upload_to_s3(video_path, os.path.basename(video_file))

        # Clean up local files
        if os.path.exists(video_path):
            os.remove(video_path)

        return jsonify({'videoUrl': s3_url})

    except Exception as e:
        logging.error(f"Error downloading Instagram post: {e}")
        return jsonify({'error': 'Failed to download Instagram post', 'details': str(e)}), 500

@app.route('/list-videos', methods=['GET'])
def list_videos_route():
    videos = get_all_videos()  # Fetch all videos from MongoDB
    return jsonify(videos)

@app.route('/get-presigned-url', methods=['GET'])
def get_presigned_url():
    file_key = request.args.get('file_key')  # Example: short_795af7cb9456400abbc9f1bad5c2b11d.mp4

    try:
        # Generate a pre-signed URL valid for 1 hour
        s3_client = boto3.client('s3',
                             region_name=AWS_S3_REGION,
                             aws_access_key_id=AWS_ACCESS_KEY,
                             aws_secret_access_key=AWS_SECRET_KEY)
        url = s3_client.generate_presigned_url('get_object',
                                        Params={'Bucket': os.getenv('AWS_S3_BUCKET'), 'Key': file_key},
                                        ExpiresIn=3600)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
