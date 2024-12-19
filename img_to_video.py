import os
import cv2
import requests
import numpy as np
from io import BytesIO
from PIL import Image
from moviepy import VideoFileClip, AudioFileClip,CompositeAudioClip

# Set path to the Google Drive folder with images (or use a directory with images)
path = "/home/pc-25/Music/Youtube-API/uploads"  # Update this path based on your directory
os.chdir(path)

# Initialize counters for mean width and height
mean_height = 0
mean_width = 0

# Counting the number of images in the directory
num_of_images = len([file for file in os.listdir('.') if file.endswith((".jpg", ".jpeg", ".png"))])
print("Number of Images:", num_of_images)
video_secs = 20

# Calculating the mean width and height of all images
for file in os.listdir('.'):
    if file.endswith((".jpg", ".jpeg", ".png")):
        im = Image.open(os.path.join(path, file))
        width, height = im.size
        mean_width += width
        mean_height += height

# Averaging width and height
mean_width = int(mean_width / num_of_images)
mean_height = int(mean_height / num_of_images)

print(f"Mean Width: {mean_width}, Mean Height: {mean_height}")

# Resizing all images to the mean width and height
for file in os.listdir('.'):
    if file.endswith((".jpg", ".jpeg", ".png")):
        im = Image.open(os.path.join(path, file))
        # Resize image using LANCZOS filter for better quality
        im_resized = im.resize((mean_width, mean_height), Image.LANCZOS)
        im_resized.save(file, 'JPEG', quality=95)
        print(f"{file} is resized")

# Function to generate a video from images
def generate_video():
    image_folder = path
    video_name = 'mygeneratedvideo.mp4'  # Output video name
    
    # Get all images in the folder
    images = [img for img in os.listdir(image_folder) if img.endswith((".jpg", ".jpeg", ".png"))]
    print("Images to be used in the video:",  float(num_of_images/video_secs))
    # Read the first image to get dimensions for the video
    frame = cv2.imread(os.path.join(image_folder, images[0]))
    height, width, layers = frame.shape

    # Create VideoWriter object to write video with correct FPS and frame size
    video = cv2.VideoWriter(video_name, cv2.VideoWriter_fourcc(*'mp4v'), float(num_of_images/video_secs), (width, height))  # 20 FPS

    # Append each image to the video
    for image in images:
        img_path = os.path.join(image_folder, image)
        video.write(cv2.imread(img_path))
        print(f"Added {image} to video")

    # Release the video file
    video.release()
    cv2.destroyAllWindows()
    vidoeClip = VideoFileClip(
        os.path.join(image_folder, video_name)
    )
    clip = AudioFileClip(
            os.path.join(image_folder, "audio.mp3")
            )
    audio = CompositeAudioClip([
        clip
        ])
    vidoeClip.audio = audio


    vidoeClip.write_videofile(
        os.path.join(image_folder, "output.mp4")
        )
    

    print(f"Video generated successfully and saved as {video_name}")

# Calling the function to generate the video
generate_video()
