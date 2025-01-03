# Use the official Python 3.12.2 image
FROM python:3.12.2-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install system dependencies required by OpenCV, ffmpeg, yt-dlp, and curl
RUN apt-get update && \
    apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    curl && \
    apt-get clean

# Ensure pip is installed and updated
RUN python3 -m ensurepip --upgrade
RUN python3 -m pip install --upgrade pip

# Install yt-dlp (YouTube video downloader) and its default extras via pip
RUN python3 -m pip install -U "yt-dlp[default]"

# Install Python dependencies from requirements.txt
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Expose a port if necessary (for example, for web apps)
EXPOSE 8000

# Run the application using gunicorn (replace 'app:app' with the appropriate entry point)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
