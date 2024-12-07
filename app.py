from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
import subprocess
import yt_dlp as youtube_dl
import instaloader
from models import mongo, init_db, save_video, get_all_videos  # Import database functions

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
COOKIE_FILE = os.getenv('COOKIE_FILE')  # Path to cookies file for authenticated requests
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')
AWS_S3_REGION = os.getenv('AWS_S3_REGION')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
MONGO_URI = os.getenv('MONGO_URI')

# Flask configurations
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MONGO_URI'] = MONGO_URI

# Initialize database
if mongo is None:
    init_db(app)

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

# Helper function to upload to AWS S3
def upload_to_s3(file_path, file_name):
    try:
        s3_client = boto3.client('s3',
                                 region_name=AWS_S3_REGION,
                                 aws_access_key_id=AWS_ACCESS_KEY,
                                 aws_secret_access_key=AWS_SECRET_KEY)
        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        file_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{file_name}"
        return file_url
    except NoCredentialsError:
        logging.error("AWS credentials not available.")
        return None
    except Exception as e:
        logging.error(f"Error uploading to S3: {e}")
        return None

# Helper function to download a social video using yt-dlp
def download_social_video(video_url, output_path, cookies_file='cookies.txt'):
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo+bestaudio/best', 
        'quiet': False,
        'verbose': True,
        'continuedl': True  # Resume downloads

    }
    cookies_path = os.path.join(os.getcwd(), 'cookies.txt')  # Assumes cookies.txt is in the root folder


    if os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_path
    else:
        ydl_opts['cookiesfrombrowser'] = ('chrome',)

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except youtube_dl.utils.DownloadError as e:
        logging.error(f"Download error: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise

# Helper function to get the duration of a video
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

# Endpoint: Process video into segments and upload
@app.route('/process-video', methods=['POST'])
def process_video():
    data = request.json
    video_url = data.get('url')
    segment_length = data.get('segment_length')

    if not video_url or not segment_length:
        return jsonify({'error': 'Missing video URL or segment length.'}), 400

    video_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.mp4")
    try:
        # Download video
        download_social_video(video_url, video_file)

        # Get video duration
        video_duration = get_video_duration(video_file)
        segment_urls = []

        # Split and upload video segments
        for start_time in range(0, int(video_duration), int(segment_length)):
            end_time = min(start_time + int(segment_length), video_duration)
            segment_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_segment.mp4")
            subprocess.run([
                'ffmpeg', '-i', video_file, '-ss', str(start_time), '-to', str(end_time), '-c', 'copy', segment_file
            ], check=True)

            s3_url = upload_to_s3(segment_file, os.path.basename(segment_file))
            if s3_url:
                segment_urls.append(s3_url)

            os.remove(segment_file)

        os.remove(video_file)

        # Save to database
        video_data = save_video(video_url, segment_length, segment_urls)

        return jsonify({'videoSegments': segment_urls})

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        return jsonify({'error': 'Failed to process video', 'details': str(e)}), 500

# Endpoint: Download Instagram video
@app.route('/download-instagram', methods=['POST'])
def download_instagram():
    data = request.json
    post_url = data.get('url')

    if not post_url:
        return jsonify({'error': 'Missing Instagram post URL.'}), 400

    try:
        # Download Instagram post
        instaloader_instance = instaloader.Instaloader()
        shortcode = post_url.split('/')[-2]
        post = instaloader.Post.from_shortcode(instaloader_instance.context, shortcode)
        download_folder = os.path.join(UPLOAD_FOLDER, "instagram")
        os.makedirs(download_folder, exist_ok=True)
        instaloader_instance.download_post(post, target=download_folder)

        # Find and upload the video
        video_file = next(
            (file for file in os.listdir(download_folder) if file.endswith('.mp4')), None)
        if video_file:
            video_path = os.path.join(download_folder, video_file)
            s3_url = upload_to_s3(video_path, video_file)
            os.remove(video_path)
            return jsonify({'videoUrl': s3_url})
        else:
            return jsonify({'error': 'No video found in post.'}), 500
    except Exception as e:
        logging.error(f"Error downloading Instagram post: {e}")
        return jsonify({'error': 'Failed to download Instagram post', 'details': str(e)}), 500

@app.route('/download-facebook', methods=['POST'])
def download_facebook():
    """
    Endpoint to download Facebook videos, reels, or posts, and store metadata in MongoDB.
    """
    data = request.json
    video_url = data.get('url')

    if not video_url:
        return jsonify({'error': 'Missing Facebook video URL.'}), 400

    try:
        # Generate a unique filename for the downloaded video
        video_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.mp4")

        # Download the Facebook video using yt-dlp
        download_social_video(video_url, video_file)

        # Verify the file was downloaded
        if not os.path.exists(video_file):
            return jsonify({'error': 'Failed to download Facebook video.'}), 500

        # Upload the video to AWS S3
        s3_url = upload_to_s3(video_file, os.path.basename(video_file))

        # Remove the local file after upload
        if os.path.exists(video_file):
            os.remove(video_file)

        # Save video metadata to MongoDB
        file_urls = [s3_url]  # Single URL in this case
        segment_length = None  # Facebook videos are not segmented by default
        video_data = save_video(video_url, segment_length, file_urls)

        if not video_data:
            return jsonify({'error': 'Failed to save video metadata.'}), 500

        return jsonify({
            'videoUrl': s3_url,
            'message':
            f"Facebook video {video_url} has been successfully downloaded and stored in MongoDB."
        })

    except youtube_dl.utils.DownloadError as e:
        logging.error(f"Download error: {e}")
        return jsonify({'error': 'Failed to download Facebook video', 'details': str(e)}), 500

    except Exception as e:
        logging.error(f"Error downloading Facebook video: {e}")
        return jsonify({'error': 'Unexpected error occurred', 'details': str(e)}), 500


# Endpoint: List videos
@app.route('/list-videos', methods=['GET'])
def list_videos():
    videos = get_all_videos()
    return jsonify(videos)

# Endpoint: Generate S3 pre-signed URL
@app.route('/get-presigned-url', methods=['GET'])
def get_presigned_url():
    file_key = request.args.get('file_key')

    try:
        s3_client = boto3.client('s3',
                                 region_name=AWS_S3_REGION,
                                 aws_access_key_id=AWS_ACCESS_KEY,
                                 aws_secret_access_key=AWS_SECRET_KEY)
        url = s3_client.generate_presigned_url('get_object', Params={
            'Bucket': AWS_S3_BUCKET,
            'Key': file_key
        }, ExpiresIn=3600)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
