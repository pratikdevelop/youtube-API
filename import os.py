import os
import boto3
from pymongo import MongoClient
from flask import Flask, render_template, request, redirect, send_from_directory
import subprocess
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)

# AWS S3 Configuration
AWS_ACCESS_KEY = 'your-aws-access-key'
AWS_SECRET_KEY = 'your-aws-secret-key'
S3_BUCKET_NAME = 'your-s3-bucket-name'
S3_REGION = 'us-west-1'  # Update with your S3 region

# MongoDB Configuration
MONGO_URI = "mongodb://localhost:27017"  # Update with your MongoDB URI
DB_NAME = "videoDB"  # Database name
COLLECTION_NAME = "videos"  # Collection name

# Set up MongoDB client
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# AWS S3 client setup
s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY,
                         aws_secret_access_key=AWS_SECRET_KEY, region_name=S3_REGION)

# Directory where uploaded media files will be stored temporarily
UPLOAD_FOLDER = 'uploads/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Directory to store generated videos
GENERATED_VIDEOS_FOLDER = 'generated_videos/'
os.makedirs(GENERATED_VIDEOS_FOLDER, exist_ok=True)

@app.route("/generate-video", methods=["POST"])
def generate_video():
    script = request.form['script']
    title = request.form['videoTitle']
    aspect_ratio = request.form['aspectRatio']
    media_files = request.files.getlist("media")
    
    # Save uploaded media files
    media_paths = []
    for media in media_files:
        media_filename = secure_filename(media.filename)
        media_path = os.path.join(UPLOAD_FOLDER, media_filename)
        media.save(media_path)
        media_paths.append(media_path)

    # Process video and generate final output based on selected aspect ratio
    video_output_path = os.path.join(GENERATED_VIDEOS_FOLDER, f"{title}.mp4")
    process_video(media_paths[0], aspect_ratio, video_output_path)

    # Upload to AWS S3 and save video metadata in MongoDB
    s3_url = upload_to_s3(video_output_path, video_output_path)
    file_urls = [s3_url]  # Only one URL in this case

    # Save video metadata in MongoDB
    segment_length = None  # Assuming no segmentation needed for Instagram videos
    video_data = save_video(title, segment_length, file_urls)

    # Redirect to a success page with the video URL
    return redirect("/success?video_url=" + s3_url)

@app.route("/success")
def success():
    video_url = request.args.get("video_url")
    return render_template("success.html", video_url=video_url)

def process_video(input_video_path, aspect_ratio, output_video_path):
    """Process the video based on aspect ratio using FFmpeg."""
    if aspect_ratio == "16:9":
        ffmpeg_command = ['ffmpeg', '-i', input_video_path, '-vf', 'scale=1920:1080', output_video_path]
    elif aspect_ratio == "4:3":
        ffmpeg_command = ['ffmpeg', '-i', input_video_path, '-vf', 'scale=1440:1080', output_video_path]
    elif aspect_ratio == "1:1":
        ffmpeg_command = ['ffmpeg', '-i', input_video_path, '-vf', 'scale=1080:1080', output_video_path]
    elif aspect_ratio == "9:16":
        ffmpeg_command = ['ffmpeg', '-i', input_video_path, '-vf', 'scale=1080:1920', output_video_path]
    elif aspect_ratio == "21:9":
        ffmpeg_command = ['ffmpeg', '-i', input_video_path, '-vf', 'scale=2560:1080', output_video_path]
    
    subprocess.run(ffmpeg_command)

def upload_to_s3(file_path, file_name):
    """Upload the video file to AWS S3 and return the URL."""
    try:
        s3_client.upload_file(file_path, S3_BUCKET_NAME, file_name)
        s3_url = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{file_name}"
        return s3_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None

def save_video(title, segment_length, file_urls):
    """Save video metadata to MongoDB."""
    video_data = {
        "title": title,
        "segment_length": segment_length,
        "file_urls": file_urls,
    }
    # Insert the video data into MongoDB
    result = collection.insert_one(video_data)
    return result.inserted_id

@app.route("/generated_videos/<filename>")
def serve_video(filename):
    return send_from_directory(GENERATED_VIDEOS_FOLDER, filename)

if __name__ == "__main__":
    app.run(debug=True)
