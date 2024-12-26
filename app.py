from io import BytesIO
import random
import string
import time
import os
import logging
import uuid
import subprocess
import requests
import yt_dlp as youtube_dl
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from botocore.config import Config
import instaloader
from werkzeug.utils import secure_filename
from PIL import Image
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
from flask_mail import Mail, Message
from flask_jwt_extended import JWTManager
from models import mongo, init_db, save_video, get_all_videos, get_video_by_id, delete_videos
import ffmpeg

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('pymongo').setLevel(logging.WARNING)

# Initialize Flask app
app = Flask(__name__)

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
jwt = JWTManager(app)
CORS(app)

# AWS and MongoDB configuration
UPLOAD_FOLDER = 'uploads'
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')
AWS_S3_REGION = os.getenv('AWS_S3_REGION')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
MONGO_URI = os.getenv('MONGO_URI')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MONGO_URI'] = MONGO_URI
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# AWS S3 client setup
config = Config(retries={'max_attempts': 10, 'mode': 'standard'})
s3_client = boto3.client('s3', region_name=AWS_S3_REGION, 
                         aws_access_key_id=AWS_ACCESS_KEY, 
                         aws_secret_access_key=AWS_SECRET_KEY, 
                         config=config)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
if mongo is None:
    init_db(app, mail_instance=mail)

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Route for home page
@app.route('/')
def index():
    return render_template('index.html')


@app.route("/youtube")
def youtube():
    return render_template("youtube.html")  # YouTube page


@app.route("/instagram")
def instagram():
    return render_template("instagram.html")  # Instagram page


@app.route("/facebook")
def facebook():
    return render_template("facebook.html")  # Facebook page


@app.route("/image-to-video")
def image_to_video():
    return render_template("image-to-video.html")  # Image to Video page


@app.route("/video-generated")
def video_generated():
    return render_template("video-generated.html")  # Video Generated by Script page


@app.route("/login")
def login():
    return render_template("login.html")  # Login page


@app.route("/signup")
def signup():
    return render_template("signup.html")  # Sign Up page


# Helper function to get the duration of a video
def get_video_duration(video_file):
    logging.debug(f"Getting duration for video file: {video_file}")
    command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_file]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def download_social_video(video_url, output_path,format_option='mp4'):
    # Set up the basic yt-dlp command with the default format option
    command = ['yt-dlp', '--output', output_path]
    command.extend(['--format', 'bv+ba/b'])
    command.extend(['--cookies', 'cookies.txt'])
    command.append(video_url)

    try:
        # Debug log for the full command
        logging.debug(f"Running yt-dlp command: {' '.join(command)}")
        
        # Run the command and capture the result
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if the download was successful
        if result.returncode == 0:
            logging.info(f"Video downloaded successfully to: {output_path}")
        else:
            logging.error(f"Error downloading video: {result.stderr}")
            raise Exception(f"Error downloading video: {result.stderr}")

    except Exception as e:
        logging.error(f"General error downloading video: {e}")
        raise


# Function to upload video to AWS S3
def upload_to_s3(file_path, file_name):
    try:
        logging.info(f"Uploading {file_name} to S3...")
        s3_client.upload_file(file_path, AWS_S3_BUCKET, file_name)
        s3_url = f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{file_name}"
        logging.info(f"File uploaded successfully to: {s3_url}")
        return s3_url
    except NoCredentialsError:
        logging.error("AWS credentials not found.")
    except PartialCredentialsError:
        logging.error("Incomplete AWS credentials.")
    except ClientError as e:
        logging.error(f"AWS client error occurred: {e}")
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}")

@app.route("/process-video", methods=["POST"])
def process_video():
    data = request.json
    video_url = data.get("url")
    segment_length = data.get(
        "segment_length", 60
    )  # Default to 60 seconds if not provided

    if not video_url:
        return jsonify({"error": "Missing video URL."}), 400

    try:
        segment_length = int(segment_length)
        if segment_length <= 0:
            raise ValueError("Segment length must be positive.")
    except ValueError as e:
        return jsonify({"error": "Invalid segment length.", "details": str(e)}), 400

    # Set the initial file paths
    video_file = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.webm")
    mp4_file = os.path.join(
        UPLOAD_FOLDER, f"{uuid.uuid4().hex}.mp4"
    )  # Converted MP4 file

    try:
        # Download the WebM video
        download_social_video(video_url, video_file, "bv+ba/b")

        # Convert WebM to MP4
        convert_webm_to_mp4(video_file, mp4_file)

        # Get the duration of the converted MP4 video
        video_duration = get_video_duration(mp4_file)
        segment_urls = []

        # Split and upload video segments
        for start_time in range(0, int(video_duration), segment_length):
            end_time = min(start_time + segment_length, int(video_duration))
            segment_file = f"{UPLOAD_FOLDER}/{uuid.uuid4().hex}_segment.mp4"

            # Create the video segment (MP4 format)
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    mp4_file,  # Input MP4 file
                    "-ss",
                    str(start_time),  # Start time for the segment
                    "-to",
                    str(end_time),  # End time for the segment
                    "-c:v",
                    "libx264",  # Video codec
                    "-c:a",
                    "aac",  # Audio codec
                    "-strict",
                    "experimental",  # Ensure AAC compatibility
                    segment_file,  # Output MP4 segment
                ],
                check=True,
            )

            # Upload the segment to S3
            s3_url = upload_to_s3(segment_file, os.path.basename(segment_file))
            if s3_url:
                segment_urls.append(s3_url)

            # Clean up the segment file after upload
            os.remove(segment_file)

        # Remove the downloaded and converted MP4 video files
        os.remove(mp4_file)
        os.remove(video_file)

        # Save video segment information to the database
        save_video(video_url, segment_length, segment_urls, "youtube")

        return jsonify({"videoSegments": segment_urls})

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        return jsonify({"error": "Failed to process video", "details": str(e)}), 500

'''def convert_webm_to_mp4(input_file, output_file):
    try:
        # Convert WebM to MP4 using FFmpeg
        ffmpeg.input(input_file).output(
            output_file,
            vcodec="libx264",
            acodec="aac",
            vprofile="baseline",
            
        ).run()
        print(f"Conversion successful: {input_file} -> {output_file}")
    except ffmpeg.Error as e:
        raise Exception(f"Error during WebM to MP4 conversion: {e}") 
replace ffmpeg  code with this 

 name, ext = os.path.splitext(mkv)
    if ext != ".mkv":
        raise Exception("Please add MKV files only!")

    output_name = name + ".mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-i", f"assets/{mkv}", "-codec", "copy", f"result/{output_name}"], check=True
        )
    except:
        raise Exception(
            "Please DOWNLOAD, INSTALL & ADD the path of FFMPEG to Environment Variables!"
        )'''


def convert_webm_to_mp4(input_file, output_file):
    name, ext = os.path.splitext(input_file)
    if ext != ".webm":
        raise Exception("Please add WEBM files only!")

    try:
        # Run FFmpeg using subprocess to convert the WebM file to MP4
        subprocess.run( [ "ffmpeg","-i", input_file,
                "-codec",
                "copy",
                "-c:v", "libx264", "-c:a", "aac", "-strict", "-2",
                output_file,
            ],
            check=True,
        )
        print(f"Conversion successful: {input_file} -> {output_file}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error during WebM to MP4 conversion: {e}")
    except FileNotFoundError:
        raise Exception(
            "Please DOWNLOAD, INSTALL & ADD the path of FFMPEG to Environment Variables!"
        )


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
        instaloader.Post.from_shortcode(instaloader_instance.context, shortcode).date_utc()

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
    url = data.get('url')
    unique_id = str(uuid.uuid4())  # Generates a random UUID
    custom_name = f"video_{unique_id}"  # Prefix with "video_" for clarity
    if not url:
        return jsonify({'error': 'Missing Facebook video URL.'}), 400

    try:
        # Setup yt-dlp options
        ydl_opts = {
            'format': 'best',  # Choose the best quality available
            'outtmpl': os.path.join(UPLOAD_FOLDER, f'{custom_name}.%(ext)s'),  # Output file template
            'quiet': True,  # Suppress yt-dlp's console output
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            # Extract video information and download
            info_dict = ydl.extract_info(url, download=True)

            video_title = info_dict.get('title', 'facebook_video')  # Get title of the video
            video_ext = info_dict.get('ext', 'mp4')  # Get file extension (e.g., mp4)
            video_file = os.path.join(UPLOAD_FOLDER, f"{custom_name}.{video_ext}")
            
            print('Video file:', video_file)

            # Check if the video file was downloaded
            

            # Optional: Implement your S3 upload logic here
            s3_url = upload_to_s3(video_file, os.path.basename(video_file))

            # Assuming save_video function is defined elsewhere to save video data to MongoDB
            video_data = save_video(url, None, [s3_url] , 'facebook')

            # Clean up local video file after upload
            if os.path.exists(video_file):
                os.remove(video_file)

            # Return success response with the S3 URL of the uploaded video
            return jsonify({
                'videoUrl': s3_url,
                'message': 'Facebook video has been successfully downloaded and stored in MongoDB.',
            })

    except youtube_dl.DownloadError as e:
        # Handle errors from youtube_dl
        return jsonify({'error': 'Failed to download Facebook video.', 'details': str(e)}), 500

    except Exception as e:
        # Handle other unexpected errors
        return jsonify({'error': 'Unexpected error occurred.', 'details': str(e)}), 500

# Endpoint: List videos
@app.route('/list-videos', methods=['GET'])
def list_videos():
    # Assuming get_videos function is defined elsewhere to retrieve video data from MongoDB
    # get Query params vairable fromthis  query list-videos?type=youtube
    query_type = request.args.get('type')
    print(f'query Type: {query_type }')

    videos = get_all_videos(type=query_type)
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

def generate_random_string(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# Define the function that generates a video from a list of image paths and adds audio
def generate_video(image_paths):
    # Dynamically create a unique video file name using current timestamp and a random string
    timestamp = int(time.time())  # Get current timestamp for uniqueness
    video_name = f"video_{timestamp}.mp4"  # Dynamic video file name

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
    output_video = f"output_{timestamp}.mp4"  # Dynamic output video file name
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], output_video)  # Video file path to be uploaded
    video_file = output_video  # The file name for the video on S3
    video_clip.write_videofile(video_path)

    print(f"Video generated successfully and saved as {output_video}")

    # Upload to S3
    s3_url = upload_to_s3(video_path, video_file)
    file_urls = [s3_url]  # Single URL in this case

    segment_length = None  # Instagram videos are not segmented by default
    video_data = save_video(output_video, segment_length, file_urls)

    print(f"Video uploaded to S3 and saved in the database: {video_data}")

    return output_video


@app.route("/delete-video/<video_id>", methods=["DELETE"])
def delete_video(video_id):
    if not video_id:
        return jsonify({"error": "Missing video ID."}), 400

    try:
        # Fetch video from the database by ID
        video = get_video_by_id(video_id)        

        if not video:
            return jsonify({"error": "Video not found."}), 404

        # If video is found, delete associated file from S3 (or your file storage)
        file_urls = video.get("file_urls", [])

        if file_urls:
            for file_url in file_urls:
                # Assuming you have a function to delete from S3
                if delete_from_s3(file_url):
                    print(f"Deleted file from S3: {file_url}")
                else:
                    logging.error(f"Failed to delete file from S3: {file_url}")

        # Now delete video record from MongoDB
        result = delete_videos(video_id)

        if result == True:
            return jsonify({"message": "Video deleted successfully."}), 200
        else:
            return jsonify({"error": "Failed to delete video from the database."}), 500

    except Exception as e:
        print(f"Error during video deletion: {e}")
        return jsonify({"error": "An error occurred while deleting the video."}), 500
def delete_from_s3(file_url):
    # If you're using AWS S3, this function deletes a file by URL (or file path) from S3
    try:
       
        file_name = file_url.split("/")[
            -1
        ]  # Assuming the file name is the last part of the URL

        response = s3_client.delete_object(Bucket=AWS_S3_BUCKET, Key=file_name)

        # Check the response
        if response["ResponseMetadata"]["HTTPStatusCode"] == 204:
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Failed to delete file from S3: {e}")
        return False


if __name__ == '__main__':
    app.run(debug=True)
