import os

# Generate a random 256-bit secret key (32 bytes) and encode it as a hexadecimal string
jwt_secret_key = os.urandom(32).hex()
print(jwt_secret_key)