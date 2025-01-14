from flask_mail import Message
from flask_pymongo import PyMongo
from datetime import datetime, timedelta
import json
import logging
import bcrypt  # For hashing passwords
from flask import jsonify, request
from itsdangerous import URLSafeTimedSerializer as Serializer  # For secure token generation
from bson import ObjectId
from flask_jwt_extended import JWTManager, create_access_token,get_jwt_identity


# Initialize PyMongo (MongoDB client)
mongo = None

# Initialize Flask-Mail (for sending emails)
mail = None
jwt = None

# Secret key for JWT token signing
SECRET_KEY = 'your_secret_key'

def init_db(app, mail_instance):
    global mongo, mail, jwt
    mongo = PyMongo(app)  # Initialize PyMongo with the app
    mail = mail_instance  # Set the mail instance for sending emails
    # Ensure the video and user collections are available in MongoDB
    mongo.db.videos.create_index([('video_url', 1)], unique=True)
    mongo.db.users.create_index([('email', 1)], unique=True)


class Video:
    def __init__(self, video_url, segment_length, file_urls, video_type):
        self.video_url = video_url
        self.segment_length = segment_length
        self.file_urls = file_urls  # This will be a JSON list of file URLs
        self.video_type = video_type  # video_Type of video
        self.created_at = datetime.utcnow()
        # self.user_id = user_id  # Add user_id field

    def to_dict(self):
        """Helper method to convert Video object to dictionary"""
        return {
            'video_url': self.video_url,
            'segment_length': self.segment_length,
            'file_urls': json.loads(self.file_urls) if isinstance(self.file_urls, str) else self.file_urls,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'video_type': self.video_type,
            # 'user_id': self.user_id  # Include user_id
        }

def save_video(video_url, segment_length, file_urls, video_type):
    video = Video(video_url, segment_length, file_urls, video_type)
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


def delete_videos(video_id): 
    try:
        mongo.db.videos.delete_one({"_id": ObjectId(video_id)})
        return True
    except Exception as e:
        print(f"Error video deletion: {e}")
        return False

def get_all_videos(video_type):
    """
    Fetch all videos of a specified type from the database.

    Args:
        video_type (str): The type of videos to fetch.

    Returns:
        list: A list of dictionaries containing video data.
    """
    try:
        # Query the database for videos of the specified type
        print(type(mongo))

        videosList = mongo.db.videos.find({"video_type": video_type})
        
        video_list = []
        
        for video in videosList:
            # Extract video data with fallbacks for missing fields
            video_url = video.get('video_url', 'N/A')
            file_urls = video.get('file_urls', ['No files available'])
            
            # Prepare video data dictionary
            video_data = {
                "id": str(video.get("_id", "Unknown ID")),
                "video_url": video_url,
                "segment_length": video.get("segment_length", "Not specified"),
                "file_urls": file_urls,
                "created_at": video.get("created_at", "Unknown time"),
                "video_type": video.get('video_type', "Not specified")
            }
            
            video_list.append(video_data)
        print(
            f"Fetched {len(video_list)} videos of type {video_type} from the database.")
        return video_list

    except Exception as e:
        print(f"Error fetching videos: {e}")
        return []



def get_video_by_id(id):
    video = mongo.db.videos.find_one({"_id": ObjectId(id)})
    if video:
        return video
    else:
        return None
    # End of video functions


# User schema (modified to work with MongoDB)
class User:
    def __init__(self, name, email, password,phone ):
        self.name = name
        self.email = email
        self.password = password  # Unhashed password
        self.phone = phone
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        """Helper method to convert User object to dictionary"""
        return {
            'name': self.name,
            'email': self.email,
            'password': self.password,  # Do NOT return unhashed password in actual use
            'phone': self.phone,
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
def save_user(name, email, password, phone):
    user = User(name, email, password, phone)
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
            'id': user['_id'],
            'name': user['name'],
            'email': user['email'],
            'password': user['password'],  # Do NOT return unhashed password in actual use
            'phone': user['phone'],
            'created_at': user['created_at']
        }
    return None

# Function to verify user password (unchanged)
def verify_user_password(email, password):
    user = get_user_by_email(email)
    if user:
        user_obj = User(user['name'], user['email'], user['password'], user['role'])
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
    print(current_user)
    user = mongo.db.users.find_one({'email': current_user})
    if not user:
       return None
    return user

# Update profile (allows the user to update their profile)
def update_profile():
    current_user = 'dd'  # Assuming you have a JWT mechanism to get current user
    data = request.json
    new_password = data.get('password')
    
    user = mongo.db.users.find_one({'name': current_user})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        mongo.db.users.update_one({'name': current_user}, {'$set': {'password': hashed_password}})
    
    return jsonify({"msg": "Profile updated"}), 200

# User login function
def user_login(email, password):
   

    if not email or not password:
        return jsonify({"msg": "Email and password are required"}), 400

    # Check if user exists
    user = get_user_by_email(email)
    if not user:
        return jsonify({"msg": "Invalid email or password"}), 401

    # Verify the password
    user_obj = User(user['name'], user['email'], user['password'], user['phone'])
    if not user_obj.check_password(password):
        return jsonify({"msg": "Invalid email or password"}), 401

    # If credentials are valid, create JWT token (assuming JWT setup is done)
    access_token = create_access_token(identity=user['email'])    
    # store this toekn in user scheam
    mongo.db.users.update_one({'email': user['email']}, {'$set': {'token':access_token}})

    return access_token