from io import BytesIO
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import uuid
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError,ClientError
from botocore.config import Config

import subprocess
import requests
import yt_dlp as youtube_dl
from werkzeug.utils import secure_filename
import instaloader
from models import mongo, init_db, save_video, get_all_videos  # Import database functions
import cv2
from PIL import Image
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('pymongo').setLevel(logging.WARNING)

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
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MONGO_URI'] = MONGO_URI
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
config = Config(
    retries={'max_attempts': 10, 'mode': 'standard'},  # Retry configuration
)

s3_client = boto3.client('s3',
                                 region_name=AWS_S3_REGION,
                                 aws_access_key_id=AWS_ACCESS_KEY,
                                 aws_secret_access_key=AWS_SECRET_KEY, 
                                 config=config)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
if mongo is None:
    init_db(app)

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

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
    print(f"result: {result}")
    return float(result.stdout.strip())

# Function to download a social media video
def download_social_video(video_url, output_path, cookies_file=None):
    """
    Downloads a video from a given URL using youtube-dl and saves it to the specified output path.
    """
    if cookies_file is None:
        cookies_file = os.path.join(os.getcwd(), 'cookies.txt') 

    # Set options for youtube_dl
    ydl_opts = {
        'outtmpl': output_path,                   
        'format': 'mp4',    
        'quiet': False,                           
        'verbose': True,                          
        'continuedl': True,         
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.19 Safari/537.36',  # Custom User-Agent
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'listformats': True,  # List all formats
    }

    # Add cookies configuration if the file exists
    ydl_opts['cookiesfrombrowser'] = ('chrome',)
    try:
        # Download the video
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except youtube_dl.utils.DownloadError as e:
        print(f"Download error: {e}")
    
    except youtube_dl.utils.ExtractorError as e:
        print(f"Extractor error: {e}")
    
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
# Endpoint: Process video into segments and upload
@app.route('/process-video', methods=['POST'])
def process_video():
    data = request.json
    video_url = data.get('url')
    segment_length = data.get('segment_length', 60)  # Default to 60 seconds if not provided

    # Validate inputs
    if not video_url:
        return jsonify({'error': 'Missing video URL.'}), 400

    try:
        segment_length = int(segment_length)
        if segment_length <= 0:
            raise ValueError("Segment length must be positive.")
    except ValueError as e:
        return jsonify({'error': 'Invalid segment length.', 'details': str(e)}), 400

    video_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.mp4")
    try:
        # Download the video
        download_social_video(video_url, video_file)

        # Get video duration
        video_duration = get_video_duration(video_file)
        segment_urls = []

        # Split and upload video segments
        for start_time in range(0, int(video_duration), segment_length):
            end_time = min(start_time + segment_length, int(video_duration))
            segment_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_segment.mp4")

            subprocess.run([
                'ffmpeg', '-i', video_file, '-ss', str(start_time), '-to', str(end_time), '-c', 'copy', segment_file
            ], check=True)

            # Upload segment to S3
            s3_url = upload_to_s3(segment_file, os.path.basename(segment_file))
            if s3_url:
                segment_urls.append(s3_url)

            os.remove(segment_file)

        # Remove the original video file after processing
        os.remove(video_file)

        # Save to database
        video_data = save_video(video_url, segment_length, segment_urls)

        # Return the list of segment URLs
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
        instaloader.Post.from_shortcode(instaloader_instance.context, shortcode)

        # Find and upload the video
        video_file = next(
            (file for file in os.listdir(UPLOAD_FOLDER) if file.endswith('.mp4')), None)

        if video_file:
            video_path = os.path.join(UPLOAD_FOLDER, video_file)
            s3_url = upload_to_s3(video_path, video_file)
            file_urls = [s3_url]  # Single URL in this case
            segment_length = None  # Instagram videos are not segmented by default
            video_data = save_video(post_url, segment_length, file_urls)                
            os.remove(video_path)
            return jsonify({'videoUrl': s3_url})
        else:
            return jsonify({'error': 'No video found in post.'}), 500
    except Exception as e:
        logging.error(f"Error downloading Instagram post: {e}")
        return jsonify({'error': 'Failed to download Instagram post', 'details': str(e)}), 500

@app.route('/download-facebook', methods=['POST'])
def download_facebook():
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
        url = s3_client.generate_presigned_url('get_object', Params={
            'Bucket': AWS_S3_BUCKET,
            'Key': file_key
        }, ExpiresIn=3600)
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Function to upload a file to AWS S3
def upload_to_s3(file_path, file_name):
    try:
        logging.info(f"Uploading {file_name} to {AWS_S3_BUCKET}...")
        
        # Perform file upload
        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        
        # Return the file URL after successful upload
        s3_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{file_name}"
        logging.info(f"File uploaded successfully: {s3_url}")
        return s3_url

    except NoCredentialsError:
        logging.error("AWS credentials not found. Please configure your credentials.")
    except PartialCredentialsError:
        logging.error("Incomplete AWS credentials provided. Please check your credentials.")
    except ClientError as e:
        logging.error(f"An AWS client error occurred: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

@app.route('/upload-images', methods=['POST'])
def upload_images():
    image_paths = []
    # Handle uploaded files
    if 'images' in request.files:
        files = request.files.getlist('images')
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                image_paths.append(file_path)
            else:
                pass

    # Handle image URLs (sent as JSON in multipart form-data)
    if 'images' in request.form:
        image_urls = request.form.getlist('images')[0].split(',')  # Get list of image URLs
        for url in image_urls:
            try:
                print(f"Processing URL: {url}")  # Debugging output

                # Download image from URL
                img_data = requests.get(url).content
                img = Image.open(BytesIO(img_data))

                # Generate a filename for the image
                filename = secure_filename(url.split("/")[-1])
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Save the image
                img.save(file_path)
                image_paths.append(file_path)
                print(f"Saved image from URL: {url} to {file_path}")

            except Exception as e:
                # Log and return error if downloading or saving fails
                return jsonify({"error": f"Failed to download image from URL: {url}, Error: {str(e)}"}), 400


    if not image_paths:
        return jsonify({"error": "No valid images uploaded or downloaded"}), 400

    # Resize images and generate video from uploaded images
    resize_images(image_paths)
    video_path = generate_video(image_paths)

    return jsonify({"message": "Video generated successfully", "video_url": video_path}), 200

# Function to resize images based on mean width and height
def resize_images(image_paths):
    mean_width = 0
    mean_height = 0
    num_of_images = len(image_paths)

    # Calculate mean width and height
    for image_path in image_paths:
        im = Image.open(image_path)
        width, height = im.size
        mean_width += width
        mean_height += height

    mean_width = int(mean_width / num_of_images)
    mean_height = int(mean_height / num_of_images)

    # Resize images
    for image_path in image_paths:
        im = Image.open(image_path)
        im_resized = im.resize((mean_width, mean_height), Image.LANCZOS)
        im_resized.save(image_path, 'JPEG', quality=95)
        print(f"{image_path} is resized")


# Function to generate a video from images
def generate_video(image_paths):
    video_name = 'mygeneratedvideo.mp4'  # Output video name
    video_secs = 20  # Duration of the video in seconds
    num_of_images = len(image_paths)

    # Read the first image to get dimensions for the video
    frame = cv2.imread(image_paths[0])
    height, width, layers = frame.shape

    # Create VideoWriter object to write video with correct FPS and frame size
    video = cv2.VideoWriter(video_name, cv2.VideoWriter_fourcc(*'mp4v'), float(num_of_images / video_secs), (width, height))  # 20 FPS

    # Append each image to the video
    for image_path in image_paths:
        video.write(cv2.imread(image_path))
        print(f"Added {image_path} to video")

    # Release the video writer
    video.release()
    cv2.destroyAllWindows()

    # Adding audio to the video
    video_clip = VideoFileClip(video_name)
    audio_clip = AudioFileClip(os.path.join(app.config['UPLOAD_FOLDER'], "audio.mp3"))
    audio = CompositeAudioClip([audio_clip])
    video_clip.audio = audio

    output_video = "output_video_with_audio.mp4"
    video_clip.write_videofile(output_video)

    print(f"Video generated successfully and saved as {output_video}")

    return output_video

if __name__ == '__main__':
    app.run(debug=True)
