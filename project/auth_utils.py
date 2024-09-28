import os
import json
import base64
import hashlib
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from ucam_webauth.raven.flask_glue import AuthDecorator

# Function to derive the decryption key
def derive_key(password: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'',  # No salt used
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

# Function to create password hash
def create_hash(password):
    hash_object = hashlib.sha256(password.encode())
    password_hash = hash_object.hexdigest()
    return password_hash

# Function to decrypt the API key
def decrypt_api_key(encrypted_data, password):
    key = base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())
    fernet = Fernet(key)
    decrypted_api_key = fernet.decrypt(encrypted_data).decode()
    return decrypted_api_key

# Load secrets from the file
def load_secrets(secrets_path=None):
    if secrets_path is None:
        # Adjust path to a level up (where .secrets is located)
        secrets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.secrets')

    print(f"Loading secrets from: {secrets_path}")

    if os.path.exists(secrets_path):
        with open(secrets_path, 'rb') as file:
            return json.load(file)
    else:
        raise ValueError("Secrets file not found!")

# Pull the decryption password from the environment
def get_decrypt_pass():
    decrypt_pass = os.environ.get('FLASK_APP_PASSWORD')
    if decrypt_pass is None:
        raise ValueError("Environment variable FLASK_APP_PASSWORD is not set")
    return decrypt_pass

# Load and validate user secrets, derive encryption key, and validate passhash
def setup_auth(secrets):
    passhash = secrets.get('passhash')
    decrypt_pass = get_decrypt_pass()
    decryptkey = derive_key(decrypt_pass)
    datacipher = Fernet(decryptkey)

    if create_hash(decrypt_pass) == passhash:
        print("Password is correct!")
    else:
        raise ValueError("Password is incorrect! Aborting!")

    # Decrypt the API credentials
    CLIENT_ID = secrets.get('api_id')
    CLIENT_SECRET = decrypt_api_key(secrets.get('api_key'), decrypt_pass)
    
    return CLIENT_ID, CLIENT_SECRET, decryptkey, datacipher

# Load authorized users and superusers
def load_users(authusers_file, superusers_file):
    with open(authusers_file, 'r') as file:
        authusers = [line.strip() for line in file.readlines()]

    with open(superusers_file, 'r') as file:
        superusers = [line.strip() for line in file.readlines()]

    return authusers, superusers

auth_decorator = AuthDecorator(desc='DCBC Ergs')

authusers_file = 'dcbc/data/auth_users.txt'
superusers_file = 'dcbc/data/super_users.txt'
authusers_def, superusers_def = load_users(authusers_file, superusers_file)

def superuser_check(crsid, superusers=superusers_def):
    if crsid in superusers:
        return True
    else:
        return False
