from flask_pymongo import PyMongo
from datetime import datetime
import json
import logging
import bcrypt  # For hashing passwords
from flask import jsonify, request
import secrets  # For generating the reset token
from itsdangerous import URLSafeTimedSerializer as Serializer  # For secure token generation
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity

# Initialize PyMongo (MongoDB client)
mongo = None

# Initialize Flask-Mail (for sending emails)
mail = None

# Secret key for JWT token signing
SECRET_KEY = 'your_secret_key'

def init_db(app, mail_instance):
    global mongo, mail
    mongo = PyMongo(app)  # Initialize PyMongo with the app
    mail = mail_instance  # Set the mail instance for sending emails
    # Ensure the video and user collections are available in MongoDB
    mongo.db.videos.create_index([('video_url', 1)], unique=True)
    mongo.db.users.create_index([('email', 1)], unique=True)


# Video schema (unchanged)
class Video:
    def __init__(self, video_url, segment_length, file_urls):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls  # This will be a JSON list of file URLs
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        """Helper method to convert Video object to dictionary"""
        return {
            'video_url': self.video_url,
            'segment_length': self.segment_length,
            'file_urls': json.loads(self.file_urls) if isinstance(self.file_urls, str) else self.file_urls,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

def save_video(video_url, segment_length, file_urls):
    video = Video(video_url, segment_length, file_urls)
    video_data = video.to_dict()
    try:
        mongo.db.videos.insert_one(video_data)
        return True
    except Exception as e:
        # Handle insertion failure
        logging.error(f"Error inserting video: {str(e)}")
        logging.error(f"Error inserting user: {str(e)}")
        return None
    
    return video_data

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


# User schema (modified to work with MongoDB)
class User:
    def __init__(self, username, email, password, role='user'):
        self.username = username
        self.email = email
        self.password = password  # Unhashed password
        self.role = role
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        """Helper method to convert User object to dictionary"""
        return {
            'username': self.username,
            'email': self.email,
            'password': self.password,  # Do NOT return unhashed password in actual use
            'role': self.role,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    def hash_password(self):
        """Hashes the user's password"""
        self.password = bcrypt.hashpw(self.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        """Compares a provided password with the hashed password"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))

# Function to save a new user (unchanged)
def save_user(username, email, password, role='user'):
    user = User(username, email, password, role)
    user.hash_password()  # Hash the password before saving

    user_data = user.to_dict()

    # Insert the user data into the MongoDB 'users' collection
    try:
        mongo.db.users.insert_one(user_data)
        return True
    except Exception as e:
        # Handle insertion failure
        logging.error(f"Error inserting user: {str(e)}")
        return None

# Function to get a user by email (unchanged)
def get_user_by_email(email):
    user = mongo.db.users.find_one({'email': email})
    if user:
        return {
            'username': user['username'],
            'email': user['email'],
            'password': user['password'],  # Do NOT return unhashed password in actual use
            'role': user['role'],
            'created_at': user['created_at']
        }
    return None

# Function to verify user password (unchanged)
def verify_user_password(email, password):
    user = get_user_by_email(email)
    if user:
        user_obj = User(user['username'], user['email'], user['password'], user['role'])
        return user_obj.check_password(password)
    return False

# Forgot password functionality
def forgot_password():
    data = request.json
    email = data['email']

    user = get_user_by_email(email)
    if not user:
        return jsonify({"msg": "Email not found"}), 404

    # Create a token for password reset
    serializer = Serializer(SECRET_KEY, salt='reset-password')
    reset_token = serializer.dumps(email, salt='reset-password')
    
    # Send the reset token via email
    reset_url = f'http://localhost:5000/reset-password/{reset_token}'
    msg = Message('Password Reset Request', recipients=[email])
    msg.body = f'Click the link to reset your password: {reset_url}'
    mail.send(msg)

    return jsonify({"msg": "Password reset link sent"}), 200

# Reset password functionality
def reset_password(token):
    try:
        # Validate the token and extract the email
        serializer = Serializer(SECRET_KEY, salt='reset-password')
        email = serializer.loads(token, max_age=3600)  # 1 hour expiry

        # Get new password from the request
        data = request.json
        new_password = data['password']

        # Update the user's password in MongoDB
        user = mongo.db.users.find_one({'email': email})
        if user:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            mongo.db.users.update_one({'email': email}, {'$set': {'password': hashed_password}})
            return jsonify({"msg": "Password reset successful"}), 200
        else:
            return jsonify({"msg": "User not found"}), 404
    except Exception as e:
        logging.error(f"Error resetting password: {str(e)}")
        return jsonify({"msg": "Invalid or expired token"}), 400

# Get profile (returns the current user's profile)
def get_profile():
    current_user = get_jwt_identity()  # Assuming you have a JWT mechanism to get current user
    user = mongo.db.users.find_one({'username': current_user})
    if not user:
        return jsonify({"msg": "User not found"}), 404
    return jsonify({"username": user['username'], "email": user['email']}), 200

# Update profile (allows the user to update their profile)
def update_profile():
    current_user = get_jwt_identity()  # Assuming you have a JWT mechanism to get current user
    data = request.json
    new_password = data.get('password')
    
    user = mongo.db.users.find_one({'username': current_user})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        mongo.db.users.update_one({'username': current_user}, {'$set': {'password': hashed_password}})
    
    return jsonify({"msg": "Profile updated"}), 200
