import secrets
from flask import Flask, request, jsonify
from flask_mail import Mail, Message
from flask_jwt_extended import jwt_required
from models import save_user, get_user_by_email, update_profile, verify_user_password, forgot_password
from flask_jwt_extended import JWTManager, create_access_token,get_jwt_identity
# User signup route
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data['username']
    password = data['password']
    email = data['email']
    try:

        # Check if the username or email already exists
        user = get_user_by_email(email=email)
        if user is not None:
            return jsonify({"msg": "Email already exists"}), 400
        newUser = save_user(username=username, email=email,password=password)
        return jsonify({"msg": "User created successfully"}), 200
    except Exception as e:
        return jsonify({"msg": "Error creating user"}), 500
        

# User signin route
@app.route('/signin', methods=['POST'])
def signin():
    data = request.json
    username = data['username']
    password = data['password']

    # Fetch the user from the database
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password, password):
        # Generate JWT token upon successful login
        access_token = create_access_token(identity=username)
        return jsonify(access_token=access_token), 200

    return jsonify({"msg": "Invalid credentials"}), 401

# Forgot password route
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data['email']

    # Check if the user exists
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "Email not found"}), 404

    # Generate a password reset token
    reset_token = secrets.token_urlsafe()
    # Send email with the reset link (you would use a real email service in production)
    reset_url = f'http://localhost:5000/reset-password/{reset_token}'
    msg = Message('Password Reset Request', recipients=[email])
    msg.body = f'Click the link to reset your password: {reset_url}'
    mail.send(msg)

    return jsonify({"msg": "Password reset link sent"}), 200

# Reset password route
@app.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    # Validate the token in a real app
    # For now, just resetting password based on the token (token validation needs to be implemented)
    data = request.json
    new_password = data['password']

    # Fetch the user and reset the password
    user = User.query.filter_by(id=token).first()  # Normally, the token would map to a user ID or email
    if not user:
        return jsonify({"msg": "Invalid or expired token"}), 400

    # Hash the new password
    hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    user.password = hashed_password
    db.session.commit()

    return jsonify({"msg": "Password reset successful"}), 200

# Profile route to get the user profile
@app.route('/profile', methods=['GET'])
@jwt_required()  # Protect the route, only accessible with a valid JWT token
def get_profile():
    current_user = get_jwt_identity()  # Get the logged-in user's identity from JWT
    user = User.query.filter_by(username=current_user).first()
    
    if not user:
        return jsonify({"msg": "User not found"}), 404
    
    return jsonify({"username": user.username, "email": user.email}), 200

# Profile route to update the user's profile (password update)
@app.route('/profile', methods=['PUT'])
@jwt_required()  # Protect the route, only accessible with a valid JWT token
def update_profile():
    current_user = get_jwt_identity()  # Get the logged-in user's identity from JWT
    data = request.json
    new_password = data.get('password')

    # Fetch the user from the database
    user = User.query.filter_by(username=current_user).first()

    if not user:
        return jsonify({"msg": "User not found"}), 404

    if new_password:
        # Hash the new password and save it
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password = hashed_password
        db.session.commit()

    return jsonify({"msg": "Profile updated successfully"}), 200

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
