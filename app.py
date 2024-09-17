import base64
import json
import os
import pickle
import random
import hashlib
import getpass
import io
import shutil

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pyotp
import qrcode
from io import BytesIO
from datetime import datetime, time, timedelta
import pyarrow as pa
import calendar

import requests
from urllib.parse import urlencode

import flask
from flask import (Flask, redirect, Blueprint, request,
                   render_template_string, send_file, url_for,
                   make_response, render_template, send_from_directory)
from flask import session as cookie_session

from bokeh.io import output_file, show
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import (Range1d, LinearAxis, ColumnDataSource, HoverTool,
                          TapTool, CustomJS, FuncTickFormatter,
                          NumeralTickFormatter, CustomJSTickFormatter)

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

from ucam_webauth.raven.flask_glue import AuthDecorator

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, select, exists, func, delete, update, asc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from models.workout import Workout # Import from models.py
from models.usersdb import User
from models.boatsdb import Boat
from models.dailydb import Daily
from models.eventdb import Event
from models.base import Base

class R(flask.Request):
    trusted_hosts = {'wp280.user.srcf.net'}

app = Flask(__name__)
app.request_class = R

app.config['SERVER_NAME'] = 'wp280.user.srcf.net'
app.config['SESSION_COOKIE_NAME'] = 'cookie_session'

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)


# Initialize the AuthDecorator
auth_decorator = AuthDecorator(desc='DCBC Ergs')

# Change the before_request behaviour to vary per request
@app.before_request
def check_authentication():
    # Skip authentication for certain routes - including coach and data sections
    if request.path.startswith('/static/') or request.path in ['/coach', '/coach/view', '/favicon.ico', '/webhook']:
        return None  # Do not require a raven login for the above
    # Otherwise, require a raven login
    return auth_decorator.before_request()

secrets = './.secrets' # API keys, etc.

if os.path.exists(secrets):
    with open(secrets, 'rb') as file:
        secrets_dict = json.load(file)
else:
    raise ValueError("secrets file not found!") # will need to manually input the secrets file

# Secrets file must contain: (in json format)
# - passhash: hashed encryption password
# - api_key : Concept2 logbook API key - from log.concept2.com/developers/keys/
# - api_id  : API client ID, encrypted with encryption password (as is above)
# - secret_key: Arbritrary secret key for flask app

passhash = secrets_dict.get('passhash')

# Pull in authorised users, and superusers. Each is a simple txt file of crsids, one value per line
authusers_file = 'data/auth_users.txt'

with open(authusers_file, 'r') as file:
    authusers = [line.strip() for line in file.readlines()]

superusers_file = 'data/super_users.txt'

with open(superusers_file, 'r') as file:
    superusers = [line.strip() for line in file.readlines()]

# Pull in the app secret key
app.secret_key = secrets_dict.get('secret_key')

# Pulls the decryption key from an environment variable - make sure this is set
decrypt_pass = os.environ.get('FLASK_APP_PASSWORD')

if decrypt_pass is None:
    raise ValueError("Environment variable FLASK_APP_PASSWORD is not set") # Will fail if not set!

# Checks the password against the hash value from .secrets
def derive_key(password: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'',  # No salt used
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

# Derive the key from the password
decryptkey = derive_key(decrypt_pass)
datacipher = Fernet(decryptkey)

def create_hash(password):
    hash_object = hashlib.sha256(password.encode())
    password_hash = hash_object.hexdigest()
    return password_hash

if create_hash(decrypt_pass) == passhash:
    print("Password is correct!")
else:
    raise ValueError("Password is incorrect! Aborting!") # Fails to load if the password is wrong

# Decrypts the API key from secrets using the password
def decrypt_api_key(encrypted_data, password):
    key = base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())
    fernet = Fernet(key)
    decrypted_api_key = fernet.decrypt(encrypted_data).decode()
    return decrypted_api_key

# Loads in the API credentials
CLIENT_ID = secrets_dict.get('api_id')
CLIENT_SECRET = decrypt_api_key(secrets_dict.get('api_key'), decrypt_pass)

# Connect to MySQL DB through SQLalchemy
SQL_PASS = secrets_dict.get('sql_pass')

engine = create_engine(f'mysql+pymysql://wp280:{SQL_PASS}@squirrel/wp280')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Callback URI after authorization on Concept2
REDIRECT_URI = 'http://wp280.user.srcf.net/callback'

# Authorization URL
AUTH_URL = 'https://log.concept2.com/oauth/authorize'

# User URL
USER_URL = 'https://log.concept2.com/api/users/me'

# Token URL
TOKEN_URL = 'https://log.concept2.com/oauth/access_token'

def flatten_data(data):
    df = pd.json_normalize(data['data'])

    if 'workout' in df.columns:
        if 'intervals' in df['workout'][0]:
            intervals_df = pd.json_normalize(
                [item for sublist in df['workout'].apply(lambda x: x.get('intervals', [])) for item in sublist],
                sep='_'
            )
        else:
            intervals_df = pd.DataFrame()

        if 'splits' in df['workout'][0]:
            splits_df = pd.json_normalize(
                [item for sublist in df['workout'].apply(lambda x: x.get('splits', [])) for item in sublist],
                sep='_'
            )
        else:
            splits_df = pd.DataFrame()

        df = df.drop(columns=['workout'])
        df = pd.concat([df, intervals_df, splits_df], axis=1)

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'],format='ISO8601')
        df = df.sort_values(by='date', ascending=True)

    return df


# Redirect 404 requests (should handle this better?)
@app.route('/<path:path>')
def catch_all(path):
    resp = make_response(redirect(url_for('login')))
    return resp


# Forbidden page - could be done more properly with exception handling!
@app.route('/sorry')
def sorry():
    return('Sorry, you don\'t have access to this page!', 403)

# Landing page
@app.route('/login')
def login():
    crsid = auth_decorator.principal

    args = request.args
    if 'crsid' in args and crsid in superusers:
        crsid = args.get('crsid')

    if crsid not in authusers:
        return(redirect(url_for('sorry'))) # bars non-authorised users from access

    file_path = f'data/{crsid}'

    # Check if the user already exists - which should have created a directory for their data
    if os.path.exists(file_path):
        token_path = f'{file_path}/token.txt' # Load in user token on login if it exists

        user = session.execute(select(User).where(User.crsid == crsid)).scalars().first()

        # Initialize the dictionary with user data from the database
        if user:
            user_data = {column.name: getattr(user, column.name) for column in User.__table__.columns}
        else:
            return render_template(template_name_or_list='welcome.html',crsid = crsid, authorized=False)

        # If the user has added their logbook account, then refresh the user access token
        # TODO: Handle the refresh-token function in a dedicated way, only when the user requests data and is denied - using a ref argument to redirect back again
        if user_data['logbook'] == True:
            if os.path.exists(token_path):
                with open(token_path, 'rb') as file:
                    encrypted_data = file.read()

                # Decrypt the data
                token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

            else:
                return(redirect(url_for('authorize')))

            authorized = 'access_token' in token_data

            if authorized:
                access_token = token_data['access_token']

                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }

                response = requests.get(USER_URL, headers=headers)  # Use GET to retrieve user data

                # Do not refresh if the user token is still valid
                if response.status_code == 200:
                    user_data = response.json()['data']

                    info_file = f'{file_path}/user_info.txt'

                    user_data_json = json.dumps(user_data)

                    # Encrypt the JSON string
                    encrypted_data = datacipher.encrypt(user_data_json.encode())

                    # Write the encrypted data to the file
                    with open(info_file, 'wb') as file:  # Note 'wb' mode for binary writing
                        file.write(encrypted_data)

                # Otherwise get a new token
                else:
                    refresh_token = token_data['refresh_token']

                    token_params = {
                        'grant_type': 'refresh_token',
                        'client_id': CLIENT_ID,
                        'client_secret': CLIENT_SECRET,
                        'scope': 'user:read,results:read',
                        'refresh_token': refresh_token
                    }

                    response = requests.post(TOKEN_URL, data=token_params)
                    token_data = response.json()

                    token_data_json = json.dumps(token_data)

                    # Encrypt the JSON string
                    encrypted_data = datacipher.encrypt(token_data_json.encode())

                    # Write the encrypted data to the file
                    with open(token_path, 'wb') as file:  # Note 'wb' mode for binary writing
                        file.write(encrypted_data)

        resp = make_response(redirect(url_for('index')))

    # Create a new user if there is no data for this user
    else:
        resp = (make_response(render_template(template_name_or_list='welcome.html', crsid = crsid, authorized=False)))

    return resp

# Handle new user creation
# Updated(!) to store user data in a SQL table - except tokens, for now at least
@app.route('/setup', methods=['GET', 'POST'])
def setup():

    crsid = auth_decorator.principal

    if crsid not in authusers:
        return(redirect(url_for('sorry'))) # TODO: automate this per request, in before_request?

    file_path = f'./data/{crsid}'

    args = request.args

    # Handle user creation without a concept2 logbook account - though this isn't really the purpose of this site at this point anyway
    if 'no-logbook' in args:

        if request.method == 'POST':

            user_data = {
                "crsid": str(crsid),
                "first_name": request.form.get("first_name"),
                "last_name": request.form.get("last_name"),
                "logbookid": request.form.get("id"),
                "color": request.form.get('color'),
                "preferred_name": request.form.get("preferred_name"),
                'squad': request.form.get('squad'),
                'bowside': request.form.get('bowside'),
                'strokeside': request.form.get('strokeside'),
                'cox': request.form.get('coxing'),
                'sculling': request.form.get('sculling'),
                'years_rowing': request.form.get('years_rowing'),
                'year': request.form.get('year'),
                'subject': request.form.get('subject'),
                "logbook": False
            }

            # Create user object with the filtered data
            new_user = User(**user_data)

            # Add (safely) to session
            session.merge(new_user)

            # Commit all inserts to the database
            session.commit()

            # Create the personal data folder [ FOR NOW? TODO]
            userpath = f'./data/{crsid}'
            if not os.path.exists(userpath):
                os.makedirs(userpath)

            return(redirect(url_for('index')))

        color = str("#"+''.join([random.choice('ABCDEF0123456789') for i in range(6)])) # assign a random RGB color per user
        return(render_template(template_name_or_list='nologbook.html', crsid=crsid, color=color)) # user creation template

    # Account creation with a logbook referral
    else:
        # This is going to need replacing, but it is low priority - would rather keep these encrypted like this for now
        token_path = f'{file_path}/token.txt'

        if not os.path.exists(token_path):
            return(redirect(url_for('login')))

        with open(token_path, 'rb') as file:
            encrypted_data = file.read()

        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

        # Using the access token, requests user information from concept2 which is used to set account data
        access_token = token_data['access_token']

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.get(USER_URL, headers=headers)  # Retrieve data from the concept2 API
        if response.status_code == 200:
            user_data = response.json()['data']
            color = str("#"+''.join([random.choice('ABCDEF0123456789') for i in range(6)])) # Give each user a random color!



            # Add the user to the SQL DB
            if not session.execute(select(exists().where(User.crsid == crsid))).scalar():
                user_data = {
                    "crsid": str(crsid),
                    "first_name": user_data.get("first_name"),
                    "last_name": user_data.get("last_name"),
                    "logbookid": user_data.get("id"),
                    "color": str(color),
                    "preferred_name": user_data.get("first_name"),
                    "logbook": True
                }

                # Create user object with the filtered data
                new_user = User(**user_data)

                # Merge to session
                session.merge(new_user)

                # Commit all inserts to the database
                session.commit()

            else: # adding a logbook after creation of a user - only change the logbook fields
                if (logbook_value := session.execute(select(User.logbook).where(User.crsid == crsid)).scalar()) == False:

                    user_data = {
                        "crsid": str(crsid),
                        "logbookid": user_data.get("id"),
                        "logbook": True
                    }

                    # Create user object with the filtered data
                    new_user = User(**user_data)

                    # Merge to session
                    session.merge(new_user)

                    # Commit all inserts to the database
                    session.commit()

            return(redirect(url_for('user_settings')))
        else:
            return(redirect(url_for('authorize')))

# Updated for SQL
@app.route('/user_settings', methods=['GET','POST'])
def user_settings():
    crsid = auth_decorator.principal

    superuser = superuser_check(crsid, superusers)

    # Check if the user exists in the database

    if not session.execute(select(exists().where(User.crsid == crsid))).scalar():
        return redirect(url_for('setup'))

    # If receiving a POST request, update the DB do that the correct values are displayed

    if request.method == 'POST':
        user_data = {
            'crsid': str(crsid),
            'logbookid': request.form.get('logid'),
            "first_name": request.form.get('first_name'),
            "last_name": request.form.get('last_name'),
            "color": request.form.get('color'),
            "preferred_name": request.form.get('preferred_name'),
            'squad': request.form.get('squad'),
            'bowside': request.form.get('bowside'),
            'strokeside': request.form.get('strokeside'),
            'cox': request.form.get('coxing'),
            'sculling': request.form.get('sculling'),
            'years_rowing': request.form.get('years_rowing'),
            'year': request.form.get('year'),
            'subject': request.form.get('subject')
        }

        # Create user object with the filtered data
        new_user = User(**user_data)

        # Merge to session
        session.merge(new_user)

        # Commit all inserts to the database
        session.commit()

    # Pull values for crsid from DB to display

    user = session.execute(select(User).where(User.crsid == crsid)).scalars().first()

    # Initialize the dictionary with user data from the database
    if user:
        personal_data = {column.name: getattr(user, column.name) for column in User.__table__.columns}
    else:
        personal_data = {column.name: None for column in User.__table__.columns}

    # Ensure 'crsid' is included in the dictionary
    personal_data['crsid'] = str(crsid)

    return(render_template(
        template_name_or_list='user.html',
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'),
        authorize = url_for('authorize'), captains = url_for('captains'), superuser=superuser,
        personal_data = personal_data))

@app.route('/home')
def index():

    crsid = auth_decorator.principal

    if not session.execute(select(exists().where(User.crsid == crsid))).scalar():
        return redirect(url_for('setup'))
    else:
        user = session.execute(select(User).where(User.crsid == crsid)).scalars().first()
        user_data = {column.name: getattr(user, column.name) for column in User.__table__.columns}

    file_path = f'./data/{crsid}'

    if not os.path.exists(f'{file_path}/token.txt') and user_data.get('logbook') == True:
        return(redirect(url_for('authorize')))

    if user_data['logbook'] == True:
        logbook = True
    else:
        logbook = False

    if crsid in superusers:
        superuser = True
    else:
        superuser = False

    return(render_template(
        template_name_or_list='home.html',
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'),
        authorize = url_for('authorize'), captains = url_for('captains'), superuser=superuser, logbook=logbook))

@app.route(f'/authorize')
def authorize():
    params = {
        'client_id': CLIENT_ID,
        'scope': 'user:read,results:read',
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI
    }
    query_string = urlencode(params)
    auth_url = f"{AUTH_URL}?{query_string}"
    return redirect(auth_url)

# Updated to SQL Handling
@app.route(f'/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'No authorization code received.'

    token_params = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }

    response = requests.post(TOKEN_URL, data=token_params)
    token_data = response.json()

    crsid = auth_decorator.principal

    userpath = f'./data/{crsid}'
    if not os.path.exists(userpath):
        os.makedirs(userpath)

    token_path = f'{userpath}/token.txt'

    token_data_json = json.dumps(token_data)

    # Encrypt the JSON string
    encrypted_data = datacipher.encrypt(token_data_json.encode())

    # Write the encrypted data to the file
    with open(token_path, 'wb') as file:  # Note 'wb' mode for binary writing
        file.write(encrypted_data)

    logbookid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    # Check if any rows exist with the given logbook id, and if so find the length
    if session.execute(select(Workout).where(Workout.user_id == logbookid)).first() is not None:
        length_wd = session.execute(select(func.count()).where(Workout.user_id == logbookid)).scalar()

        resp = make_response(render_template_string('''
            <h1>Reload Data?</h1>
            <p>You have already previously loaded data, and you have {{ length_wd }} workouts loaded </p>
            <p><b>New workouts will sync automatically!</b></p>
            <p><a href = "{{ url_for('load_all') }}"> I'm sure, load data</a></p>
            <p><a href = "{{ url_for('index') }}">Go Home</a></p>
        ''', length_wd = length_wd))

        return resp

    else:
        resp = make_response(redirect(url_for("load_all")))

        return resp

# Updated to SQL Handling
@app.route(f'/load_all')
def load_all():

    crsid = auth_decorator.principal

    args = request.args
    if 'crsid' in args and crsid in superusers:
        crsid = args.get('crsid')

    file_path = f'./data/{crsid}'

    token_path = f'{file_path}/token.txt'

    if os.path.exists(token_path):
        with open(token_path, 'rb') as file:
            encrypted_data = file.read()

        # Decrypt the data
        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']

    data_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    reset_all=True

    data_params = {
        "from": '2000-01-01',
        "to": '2040-01-01'
    }

    data_url = "https://log.concept2.com/api/users/me/results"

    response = requests.get(data_url, headers=data_headers, params=data_params)

    dataresponse = response.json()

    if 'data' not in dataresponse:
        token_params = {
            'grant_type': 'refresh_token',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scope': 'user:read,results:read',
            'refresh_token': refresh_token
        }

        response = requests.post(TOKEN_URL, data=token_params)
        token_data = response.json()

        token_data_json = json.dumps(token_data)

        # Encrypt the JSON string
        encrypted_data = datacipher.encrypt(token_data_json.encode())

        # Write the encrypted data to the file
        with open(token_path, 'wb') as file:  # Note 'wb' mode for binary writing
            file.write(encrypted_data)

        data_headers = {
            'Authorization': f'Bearer {token_data["access_token"]}',
            'Content-Type': 'application/json'
        }

        response = requests.get(data_url, headers=data_headers)

        dataresponse = response.json()

        if 'data' not in dataresponse:
            return(f'error - response is {dataresponse["status_code"]}, expected 200')

    data_json = dataresponse.get('data')

    if len(data_json) == 50:
        len_recover = 50

        while len_recover != 1:
            old_set = data_json[-1].get('date')

            data_params = {
            "from": '2000-01-01',
            "to": old_set,
            "type": "rower",
            }

            response = requests.get(data_url, headers=data_headers, params=data_params)

            dataresponse = response.json()

            len_recover = len(flatten_data(dataresponse))

            this_json = dataresponse.get('data')
            data_json += this_json

    # SQL Version!

    from models.workout import Workout, Base

    allowed_keys = {'id', 'user_id', 'date', 'distance', 'type', 'time', 'comments', 'heart_rate', 'stroke_rate', 'stroke_data'}

    workouts = data_json

    for workout_data in workouts:
        filtered_workout_data = {
            "id": workout_data.get("id"),
            "user_id": workout_data.get("user_id"),
            "date": workout_data.get("date", None),  # Use None as a default
            "distance": workout_data.get("distance", None),
            "type": workout_data.get("type", None),
            "workout_type": workout_data.get("workout_type", None),
            "time": workout_data.get("time", None),
            "spm": workout_data.get("stroke_rate", None),
            "avghr": workout_data.get("heart_rate", {}).get("average", None),
            "comments": workout_data.get("comments", None),    # If missing, default to None
            "stroke_data": workout_data.get("stroke_data", False)
        }

        # Convert date string to datetime object if it's not None
        if filtered_workout_data["date"]:
            filtered_workout_data["date"] = datetime.strptime(filtered_workout_data["date"], "%Y-%m-%d %H:%M:%S")

        existing_workout = session.query(Workout).filter_by(id=filtered_workout_data['id']).first()
        if existing_workout:
            print(f"Record with id {filtered_workout_data['id']} already exists. Skipping insertion.")
            continue  # Skip this record

        # Create Workout object with the filtered data
        new_workout = Workout(**filtered_workout_data)

        # Add to session
        session.merge(new_workout)

    # Commit all inserts to the database
    session.commit()

    return redirect(url_for('setup'))

# Updated to SQL Handling - should be and was easy
@app.route('/webhook', methods=['POST'])
def webhook():
    # Attempt to parse the incoming JSON
    if request.is_json:
        webhook_data = request.get_json()

        # Get the type of event and the result payload
        event_type = webhook_data.get('type')

        if event_type != 'result-deleted':
            workout_data = webhook_data.get('result')

            filtered_workout_data = {
                "id": workout_data.get("id"),
                "user_id": workout_data.get("user_id"),
                "date": workout_data.get("date", None),  # Use None as a default
                "distance": workout_data.get("distance", None),
                "type": workout_data.get("type", None),
                "workout_type": workout_data.get("workout_type", None),
                "time": workout_data.get("time", None),
                "spm": workout_data.get("stroke_rate", None),
                "avghr": workout_data.get("heart_rate", {}).get("average", None),
                "comments": workout_data.get("comments", None),    # If missing, default to None
                "stroke_data": workout_data.get("stroke_data", False)
            }

            # Convert date string to datetime object if it's not None
            if filtered_workout_data["date"]:
                filtered_workout_data["date"] = datetime.strptime(filtered_workout_data["date"], "%Y-%m-%d %H:%M:%S")

            # Create Workout object with the filtered data
            new_workout = Workout(**filtered_workout_data)

            # Add to session
            session.merge(new_workout)

            # Commit all inserts to the database
            session.commit()
            webhook_data = request.get_json()

        else:
            result_id = webhook_data.get('result_id')

            session.execute(delete(Workout).where(Workout.id == result_id))
            session.commit()

        return "Result updated", 200

    else:
        print("Received non-JSON Payload")
        return "Invalid content type", 400

# Updated to SQL! Errors might need testing
@app.route(f'/plot', methods=['GET', 'POST'])
def plot():

    usrid = auth_decorator.principal
    args = request.args

    otherview = False

    superuser = superuser_check(usrid, superusers)

    if 'crsid' in args and usrid in superusers:
        crsid = args.get('crsid')
        otherview = True
    elif 'crsid' in args and usrid not in superusers:
        if usrid == args.get('crsid'):
            crsid = usrid
        else:
            return(redirect(url_for('forbidden', ref=f'/plot?crsid={args.get("crsid")}')))
    else:
        crsid = auth_decorator.principal

    file_path = f'./data/{crsid}'

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    query = select(Workout).where(Workout.user_id == logid)

    # Use pandas to read the query result into a DataFrame
    df = pd.read_sql(query, engine)

    if logid is None:
        if session.execute(select(User.crsid).where(User.crsid == crsid)).scalars().first() is None and otherview:
            return(render_template(
                template_name_or_list='plot.html',
                script=[''],
                div=[f' <p>No specified user <b>{crsid}</b> found!<a href={ url_for("index")}> Return to home </a></p>'],
                otherview=otherview, crsid=crsid,
                club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

        return(render_template(
            template_name_or_list='plot.html',
            script=[''],
            div=[f'No user found! <p><a href={ url_for("login")}> Return to login </a></p>'],
            otherview=otherview, crsid=crsid,
            club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

    if df is None:
        if session.execute(select(User.crsid).where(User.crsid == crsid)).scalars().first() is None and otherview:
            return(render_template(
                template_name_or_list='plot.html',
                script=[''],
                div=[f'No specified user data found! <p><a href={ url_for("index")}> Return to home </a></p>'],
                otherview=otherview, crsid=crsid,
                club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

        return(render_template(
            template_name_or_list='plot.html',
            script=[''],
            div=[f'No data found! Check you have logged some ergs before coming here. <p><a href={ url_for("index")}> Return to home </a></p>'],
            otherview=otherview, crsid=crsid,
            club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

    df['date'] = pd.to_datetime(df['date'])
    df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

    df['split'] = round((df['time'] / 10) / (df ['distance'] / 500),1)

    if 'from_date' in args and 'to_date' in args:
        from_date = args.get('from_date')
        to_date = args.get('to_date')

    else:
        from_date = datetime.strptime('2024-10-01', '%Y-%m-%d')
        to_date = datetime.strptime('2025-06-30', '%Y-%m-%d')

    df = df[(df['date'] >= from_date) & (df['date'] <= to_date)]

    def format_seconds(seconds):
        # Calculate minutes, seconds, and tenths of seconds
        minutes = int(seconds // 60)
        seconds_remainder = seconds % 60
        seconds_int = int(seconds_remainder)
        tenths = int((seconds_remainder - seconds_int) * 10)

        # Format the result as "minutes:seconds.tenths"
        return f"{minutes}:{seconds_int:02d}.{tenths}"

    df['split'] = df['split'].apply(format_seconds)

    df = df.sort_values("date")

    p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

    # Plot the second dataset on the right y-axis
    p1.line(
        df['date'],
        df['distance'].cumsum(),
        color='magenta',
        alpha=0.8,
        line_width=3)


    p1.yaxis.formatter = NumeralTickFormatter(format='0.0a')

    one_day = 24 * 60 * 60 * 1000

    df['date_day'] = df['date'].dt.floor('D')
    df['cumsum'] = df.groupby('date_day')['distance'].cumsum()
    df['base'] = df['cumsum'] - df['distance']

    # Create a ColumnDataSource
    source = ColumnDataSource(df)

    p1.extra_y_ranges = {"daily": Range1d(start=0, end=df['cumsum'].max())}
    p1.add_layout(LinearAxis(y_range_name="daily", axis_label="Daily Metres"), 'right')

    # Set the width to 1 day in milliseconds
    one_day = 24 * 60 * 60 * 1000

    # Plot the stacked bars
    p1.vbar(x='date_day',
           top='cumsum',
           bottom='base',
           width=one_day,
           color='grey',
           alpha=0.8,
           source=source,
           y_range_name='daily')

    hover = HoverTool(tooltips=[
        ("Date", "@date_day{%F}"),
        ("Distance", "@distance"),
        ("Split", "@split"),
    ], formatters={
        '@date_day': 'datetime',  # use 'datetime' formatter for '@date_day' field
    }, mode='mouse',renderers=[p1.renderers[1]])

    callback = CustomJS(args={'source': source, 'crsid':crsid}, code="""
        console.log('CustomJS callback triggered');

        // Access the ColumnDataSource
        var data = source.data;

        // Access the selected indices
        var selected_indices = source.selected.indices;

        if (selected_indices.length > 0) {
            var index = selected_indices[0];
            var item_id = data['id'][index];

            // Redirect to the Flask route with item_id as a parameter
            window.location.href = '/workout?id=' + item_id + '&crsid=' + crsid;
        } else {
            console.log('No item selected');
        }
    """)
    # Add TapTool with the CustomJS callback
    tap_tool = TapTool(callback=callback)
    p1.add_tools(tap_tool)

    p1.add_tools(hover)

    script1, div1 = components(p1)

    return(render_template(
        template_name_or_list='plot.html',
        script=[script1],
        div=[div1],
        df=df, otherview=otherview, crsid=crsid, superuser=superuser,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

# Updated to SQL
@app.route('/data')
def data():
    crsid = auth_decorator.principal

    args = request.args

    superuser=False
    if superuser_check(crsid, superusers):
        superuser=True
        if 'crsid' in args:
            crsid = args.get('crsid')

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    query = select(Workout).where(Workout.user_id == logid)

    # Use pandas to read the query result into a DataFrame
    df = pd.read_sql(query, engine)

    df['date'] = pd.to_datetime(df['date'])
    df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

    df['split'] = round((df['time'] / 10) / (df ['distance'] / 500),1)

    if 'from_date' in args and 'to_date' in args:
        from_date = args.get('from_date')
        to_date = args.get('to_date')

    else:
        from_date = '2024-01-01'
        to_date = '2024-12-31'

    df = df[(df['date'] >= from_date) & (df['date'] <= to_date)]

    df['split'] = df['split'].apply(format_seconds)

    totaldist = df['distance'].sum()
    totaltime = format_seconds((df['time'].sum())/10)

    df['time'] = (df['time']/10).apply(format_seconds)

    df = df.sort_values("date")

    max_select = ['id','date','distance','time','split','spm','type','workout_type','avghr','comments']
    selects = []

    for item in max_select:
        if item in df.keys():
            selects.append(item)

    subdf = df[selects].copy()

    headers = ['id','Date','Distance','Time','Split / 500m','Stroke Rate','Type','Workout Type','Average HR','Comments']

    # Apply the function to each cell in the DataFrame
    if 'stroke_rate' in subdf:
        subdf['stroke_rate'] = subdf['stroke_rate'].apply(lambda x: int(x) if isinstance(x, (float, int)) and not pd.isna(x) else x)

    subdf.replace({np.nan: None, 'unknown': None}, inplace=True)

    subdf_dict = subdf.to_dict(orient='records')

    return render_template('data.html', data=subdf_dict, crsid=crsid, superuser=superuser,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'), headers=headers, totaldist=totaldist, totaltime=totaltime)

# Updated to SQL
@app.route('/workout')
def workout():

    usrid = auth_decorator.principal
    args = request.args

    otherview = False

    if 'id' in args:
        workoutid = args.get('id')

    else:
        return(redirect(url_for('plot')))


    if 'crsid' in args and usrid in superusers:
        crsid = args.get('crsid')
        otherview = True
    elif 'crsid' in args and usrid not in superusers:
        if usrid == args.get('crsid'):
            crsid = usrid
        else:
            return(redirect(url_for('forbidden', ref=f'/workout?id={workoutid}&crsid={args.get("crsid")}')))
    else:
        crsid = auth_decorator.principal

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    data_url = f"https://log.concept2.com/api/users/{logid}/results/{workoutid}"

    file_path = f'./data/{crsid}'

    token_path = f'{file_path}/token.txt'

    if os.path.exists(token_path):
        with open(token_path, 'rb') as file:
            encrypted_data = file.read()

        # Decrypt the data
        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']

    data_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(data_url, headers=data_headers)

    dataresponse = response.json()

    if 'data' not in dataresponse:
        token_params = {
            'grant_type': 'refresh_token',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scope': 'user:read,results:read',
            'refresh_token': refresh_token
        }

        response = requests.post(TOKEN_URL, data=token_params)
        token_data = response.json()

        token_data_json = json.dumps(token_data)

        # Encrypt the JSON string
        encrypted_data = datacipher.encrypt(token_data_json.encode())

        # Write the encrypted data to the file
        with open(token_path, 'wb') as file:  # Note 'wb' mode for binary writing
            file.write(encrypted_data)

        data_headers = {
            'Authorization': f'Bearer {token_data["access_token"]}',
            'Content-Type': 'application/json'
        }

        response = requests.get(data_url, headers=data_headers)

        dataresponse = response.json()

        if 'data' not in dataresponse:
            return(f'error - response is {dataresponse["status_code"]}, expected 200')

    res = dataresponse['data']

    if res['stroke_data']:
        stroke_url = f"https://log.concept2.com/api/users/{logid}/results/{workoutid}/strokes"

        data_headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.get(stroke_url, headers=data_headers)

        strokeresponse = response.json()

        if 'data' not in dataresponse:
            token_params = {
                'grant_type': 'refresh_token',
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'scope': 'user:read,results:read',
                'refresh_token': refresh_token
            }

            response = requests.post(TOKEN_URL, data=token_params)
            token_data = response.json()

            token_data_json = json.dumps(token_data)

            # Encrypt the JSON string
            encrypted_data = datacipher.encrypt(token_data_json.encode())

            # Write the encrypted data to the file
            with open(token_path, 'wb') as file:  # Note 'wb' mode for binary writing
                file.write(encrypted_data)

            data_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(stroke_url, headers=data_headers)

            strokeresponse = response.json()

        strokes = flatten_data(strokeresponse)

        p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

        p1.y_range = Range1d(start=(strokes['p'].min()*0.8)/10, end=(strokes['p'].max()*1.2)/10)
        # Plot the second dataset on the right y-axis
        p1.line(
            strokes['t']/10,
            strokes['p']/10,
            color='magenta',
            alpha=0.8,
            line_width=3)

        p1.extra_y_ranges = {"spm": Range1d(start=0, end=strokes['spm'].max()*1.2)}
        p1.add_layout(LinearAxis(y_range_name="spm", axis_label="Strokes per Minute"), 'right')

        p1.line(
            strokes['t']/10,
            strokes['spm'],
            color='grey',
            alpha=0.8,
            line_width=3,
            y_range_name='spm')

        p1.xaxis.formatter = CustomJSTickFormatter(code="""
            var minutes = Math.floor(tick / 60);
            var seconds = (tick % 60).toFixed(1);
            return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
        """)

        p1.yaxis[0].formatter = CustomJSTickFormatter(code="""
            var minutes = Math.floor(tick / 60);
            var seconds = (tick % 60).toFixed(1);
            return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
        """)

        script1, div1 = components(p1)

    else:
        strokes = pd.DataFrame()
        script1 = ''
        div1 = 'No stroke data found!'

    max_select = ['id','date','distance','time','split','stroke_rate','workout_type','heart_rate.average','comments']
    selects = []

    headers_mapping = {
        'id': 'ID',
        'date': 'Date',
        'distance': 'Distance',
        'time': 'Time',
        'split': 'Split / 500m',
        'stroke_rate': 'Stroke Rate',
        'workout_type': 'Type',
        'heart_rate.average': 'Average HR',
        'comments': 'Comments'
    }

    for item in max_select:
        # Handle nested dictionary case for 'heart_rate.average'
        if '.' in item:
            keys = item.split('.')
            value = res.get(keys[0], {}).get(keys[1], None)
        else:
            value = res.get(item, None)

        # Append to `selects` if the item exists in `res` and is not empty or invalid
        if value not in ['', np.nan, None, [], {}]:
            selects.append(item)

    resdict = {k: res[k] if '.' not in k else res[k.split('.')[0]][k.split('.')[1]] for k in selects}

    # Filter headers based on `selects`
    filtered_headers = [headers_mapping[item] for item in selects]

    return(render_template(
        template_name_or_list='workout.html',
        script=[script1],
        div=[div1],
        df=strokes,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'),
        headers=filtered_headers, data=resdict))

# Updated for SQL
@app.route('/club')
def club():
    crsids = session.execute(select(User.crsid)).scalars().all()
    args = request.args

    dfs = []

    totaldist = 0
    totaltime = 0

    if 'from_date' in args and 'to_date' in args:
        from_date = args.get('from_date')
        to_date = args.get('to_date')

    else:
        from_date = datetime.strptime('2024-10-01', '%Y-%m-%d')
        to_date = datetime.strptime('2025-06-30', '%Y-%m-%d')

    for crsid in crsids:
        logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

        query = select(Workout).where(Workout.user_id == logid)

        userdf = pd.read_sql(query, engine)

        userdf['date'] = pd.to_datetime(userdf['date'])
        userdf['distance'] = pd.to_numeric(userdf['distance'], errors='coerce')

        userdf = userdf[(userdf['date'] >= from_date) & (userdf['date'] <= to_date)]

        tdf = pd.DataFrame({f'{crsid}_date': userdf['date'],
                            f'{crsid}_distance': userdf['distance']})

        tdf = tdf.sort_values(f'{crsid}_date')

        dfs.append(tdf)

        totaldist += userdf['distance'].sum()
        totaltime += userdf['time'].sum()

    totaltime = format_seconds(totaltime/10)

    try:
        clubdf = pd.concat(dfs, axis=0, ignore_index=True)
    except:
        return(render_template(
        template_name_or_list='club.html',
        script='',
        div=['<p>No user data found! Make sure some data exists. </p>'], totaldist = 0, totaltime = 0,
        clubdf = [], superuser = superuser_check(auth_decorator.principal, superusers),
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

    p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

    for crsid in crsids:
        if f'{crsid}_date' not in clubdf:
            continue

        date=clubdf[f'{crsid}_date']
        distance=clubdf[f'{crsid}_distance'].cumsum()
        idcolor = session.execute(select(User.color).where(User.crsid == crsid)).scalar()
        idname = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

        source = ColumnDataSource(data=dict(
            x=date,
            y=distance,
            legend_label=[idname] * len(date)  # Repeat crsid for each data point
        ))

        p1.line(
            x='x',
            y='y',
            source=source,
            alpha=0.8,
            line_width=3,
            line_color=idcolor)


    hover = HoverTool(tooltips=[
        ('Name','@legend_label')
    ], mode='mouse')

    p1.add_tools(hover)

    p1.yaxis.formatter = NumeralTickFormatter(format='0.0a')

    script1, div1 = components(p1)

    return(render_template(
        template_name_or_list='club.html',
        script=[script1],
        div=[div1], totaldist = totaldist, totaltime = totaltime,
        clubdf = clubdf, superuser = superuser_check(auth_decorator.principal, superusers),
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

@app.route('/forbidden')
def forbidden():
    crsid = auth_decorator.principal

    data = None

    try:
        data = request.args
    except:
        pass

    if data:
        ref = data['ref']

    return render_template_string('''
        <h2>You are signed in:{{ crsid }}</h2>

        <p>Sorry, you don't have access to the page {{ref}}!</p>

        <p><a href="{{ url_for('index')}}"> Go home </a></p>

    ''', crsid=crsid, ref=ref)

# Update for SQL
@app.route('/pbs')
def pbs():
    crsid = auth_decorator.principal

    file_path = f'./data/{crsid}'

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    query = select(Workout).where(Workout.user_id == logid)

    # Use pandas to read the query result into a DataFrame
    df = pd.read_sql(query, engine)

    df['date'] = pd.to_datetime(df['date'])
    df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

    df['split'] = round((df['time'] / 10) / (df ['distance'] / 500),1)


    def format_seconds(seconds):
        # Calculate minutes, seconds, and tenths of seconds
        minutes = int(seconds // 60)
        seconds_remainder = seconds % 60
        seconds_int = int(seconds_remainder)
        tenths = int((seconds_remainder - seconds_int) * 10)

        # Format the result as "minutes:seconds.tenths"
        return f"{minutes}:{seconds_int:02d}.{tenths}"

    df['split'] = df['split'].apply(format_seconds)

    df['time_readable'] = (df['time']/10).apply(format_seconds)

    df = df.sort_values("date")

    two_ks = df[(df['workout_type'] == 'FixedDistanceSplits') & (df['distance'] == 2000)]
    five_ks = df[(df['workout_type'] == 'FixedDistanceSplits') & (df['distance'] == 5000)]

    if not two_ks.empty:

        p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

        # Plot the second dataset on the right y-axis
        p1.scatter(
            x=two_ks['date'],
            y=two_ks['time']/10,
            color='black',
            alpha=0.8)

        time_array = two_ks['time'].values
        keep_indices = np.where(np.r_[True, time_array[1:] < np.minimum.accumulate(time_array[:-1])])[0]

        # Slice the DataFrame
        pb_twos = two_ks.iloc[keep_indices].copy()

        p1.line(
            x=pb_twos['date'],
            y=pb_twos['time']/10,
            color='magenta',
            alpha=0.8,
            line_width=3)

        p1.yaxis.formatter = FuncTickFormatter(code="""
            var minutes = Math.floor(tick / 60);
            var seconds = (tick % 60).toFixed(1);
            return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
        """)

        script1, div1 = components(p1)
    else:
        script1 = ''
        div1 = 'Log a 2K to see your PBs!'

    if not five_ks.empty:

        p2 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

        # Plot the second dataset on the right y-axis
        p2.scatter(
            x=five_ks['date'],
            y=five_ks['time']/10,
            color='black',
            alpha=0.8)

        time_array = five_ks['time'].values
        keep_indices = np.where(np.r_[True, time_array[1:] < np.minimum.accumulate(time_array[:-1])])[0]

        # Slice the DataFrame
        pb_fives = five_ks.iloc[keep_indices].copy()

        p2.line(
            x=pb_fives['date'],
            y=pb_fives['time']/10,
            color='magenta',
            alpha=0.8,
            line_width=3)

        p2.yaxis.formatter = FuncTickFormatter(code="""
            var minutes = Math.floor(tick / 60);
            var seconds = (tick % 60).toFixed(1);
            return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
        """)

        script2, div2 = components(p2)

    else:
        script2 = ''
        div2 = 'Log a 5K to see your PBs!'

    return(render_template(
        template_name_or_list='pbs.html',
        script=[script1, script2],
        div=[div1, div2],
        two_ks = two_ks, five_ks = five_ks,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

@app.route('/coach')
def coach():
    coach_file = './data/coaches.txt'
    approved_file = './data/approved_coaches.txt'

    args = request.args
    username = None
    if 'username' in args:
        username = args.get('username')

    notfound=False
    if 'notfound' in args:
        notfound = args.get('notfound')

    code = False
    if 'tfa_code' in args:
        code = args.get('tfa_code')

    if not username or notfound:
        return render_template_string('''
            <h1>Welcome to the Coach Environment</h1>
            {% if notfound %}
                <h2>User not found, try again!</h2>
            {% endif %}
            <form method="get" action="{{ url_for('coach') }}">
                <label for="crsid">Username:</label>
                <input type="text" id="username" name="username" required>
                <input type="submit" value="View">
            </form>
        ''', notfound=notfound)

    if not os.path.exists(coach_file) or os.path.getsize(coach_file) == 0:
        with open(coach_file, 'w') as file:
            json.dump({}, file)  # Initialize with an empty dictionary

    with open(coach_file, 'r') as file:
        coaches = json.load(file)

    if not os.path.exists(approved_file):
        return("Approved coaches file is missing!")

    with open(approved_file, 'r') as file:
        approved_coaches = [line.strip() for line in file.readlines()]

    if username not in approved_coaches:
        return(redirect(url_for('coach', username=username, notfound=True)))

    def update_coaches(coaches):
        with open(coach_file, 'w') as file:
            json.dump(coaches, file)

    def get_coach(name, coaches):
        return coaches.get(name)

    def update_coach(name, data, coaches):
        coaches[name] = data
        update_coaches(coaches)

    def generate_totp_secret():
        return pyotp.random_base32()

    def create_coach(coach, coaches):
        if coach in coaches:
            return False
        else:
            secret = generate_totp_secret()
            coaches[coach] = {
                'username': coach,
                '2FA_secret': secret,
                'app_added': False
                }
            update_coaches(coaches)
            return True

    create_coach(username, coaches)

    apped = coaches[username]['app_added']

    def generate_qr_code(username, coaches):
        user = get_coach(username, coaches)
        if not user:
            return None
        totp = pyotp.TOTP(user['2FA_secret'])
        uri = totp.provisioning_uri(username, issuer_name="DCBC Ergs Coach")
        qr = qrcode.make(uri)
        buffer = BytesIO()
        qr.save(buffer)
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def verify_2fa(username, code, coaches):
        user = get_coach(username, coaches)
        totp = pyotp.TOTP(user['2FA_secret'])
        return totp.verify(code)

    if code != False:
        if verify_2fa(username, code, coaches):
            cookie_session['authenticated'] = True

            user = get_coach(username, coaches)
            if not user['app_added']:
                user['app_added'] = True
                coaches[username] = user
                update_coaches(coaches)

            return(redirect(url_for('coachview', username=username)))
        else:
            return(render_template_string('''
                2FA Failed!

                <a href={{ url_for('coach') }}> Go back </a>
            '''))

    qr_code_base64 = generate_qr_code(username, coaches)
    qr_code_url = f'data:image/png;base64,{qr_code_base64}' if qr_code_base64 else None

    return(render_template_string('''
            <!-- enable_2fa.html -->
            {% if username %}
                {% if not apped %}
                    <img src="{{ qrcode }}" alt="Scan this QR code with your Authenticator app">
                    <p>After scanning the QR code, enter the code generated by your authenticator app:</p>
                {% else %}
                    <p>Enter the code from your authenticator app:</p>
                {% endif %}
                <form method="get" action="{{ url_for('coach', username=username, code=tfa_code) }}">
                    <input type="text" name="tfa_code" required>
                    <input type="hidden" name="username" value="{{ username }}">
                    <button type="submit">Verify</button>
                </form>
            {% endif %}
    ''', username=username, qrcode=qr_code_url, apped=apped))

@app.route('/coach/view')
def coachview():
    if not cookie_session.get('authenticated'):
        return(render_template_string('''
            <h1>Session is not authenticated!</h1>
            <p><a href="{{ url_for('coach')}}"> Try logging in again! </a></p>
        '''))
    else:
        crsids = session.execute(select(User.crsid)).scalars().all()
        args = request.args

        dfs = []

        totaldist = 0
        totaltime = 0

        if 'from_date' in args and 'to_date' in args:
            from_date = args.get('from_date')
            to_date = args.get('to_date')

        else:
            from_date = datetime.strptime('2024-10-01', '%Y-%m-%d')
            to_date = datetime.strptime('2025-06-30', '%Y-%m-%d')

        for crsid in crsids:
            logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

            query = select(Workout).where(Workout.user_id == logid)

            userdf = pd.read_sql(query, engine)

            userdf['date'] = pd.to_datetime(userdf['date'])
            userdf['distance'] = pd.to_numeric(userdf['distance'], errors='coerce')

            userdf = userdf[(userdf['date'] >= from_date) & (userdf['date'] <= to_date)]

            tdf = pd.DataFrame({f'{crsid}_date': userdf['date'],
                                f'{crsid}_distance': userdf['distance']})

            tdf = tdf.sort_values(f'{crsid}_date')

            dfs.append(tdf)

            totaldist += userdf['distance'].sum()
            totaltime += userdf['time'].sum()

        totaltime = format_seconds(totaltime/10)

        try:
            clubdf = pd.concat(dfs, axis=0, ignore_index=True)
        except:
            return(render_template(
            template_name_or_list='club.html',
            script='',
            div=['<p>No user data found! Make sure some data exists. </p>'], totaldist = 0, totaltime = 0,
            clubdf = [], superuser = superuser_check(auth_decorator.principal, superusers),
            club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

        p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

        for crsid in crsids:
            if f'{crsid}_date' not in clubdf:
                continue

            date=clubdf[f'{crsid}_date']
            distance=clubdf[f'{crsid}_distance'].cumsum()
            idcolor = session.execute(select(User.color).where(User.crsid == crsid)).scalar()
            idname = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

            source = ColumnDataSource(data=dict(
                x=date,
                y=distance,
                legend_label=[idname] * len(date)  # Repeat crsid for each data point
            ))

            p1.line(
                x='x',
                y='y',
                source=source,
                alpha=0.8,
                line_width=3,
                line_color=idcolor)


        hover = HoverTool(tooltips=[
            ('Name','@legend_label')
        ], mode='mouse')

        p1.add_tools(hover)

        p1.yaxis.formatter = NumeralTickFormatter(format='0.0a')

        script1, div1 = components(p1)

        return(render_template(
            template_name_or_list='coach.html',
            script=[script1],
            div=[div1], totaldist = totaldist, totaltime = totaltime,
            clubdf = clubdf, superuser = superuser_check(auth_decorator.principal, superusers),
            club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

@app.route('/captains', methods=['GET', 'POST'])
def captains():
    crsid = auth_decorator.principal
    users = session.execute(select(User)).scalars().all()

    def format_tags(tags):
        if tags:
            return tags.replace(',', ' ').replace(' ', '-').lower()
        return ''

    app.jinja_env.filters['format_tags'] = format_tags

    if crsid not in superusers:
        return redirect(url_for('forbidden', ref='captains'))

    if request.method == 'POST':
        # Retrieve all user CRSID values
        user_crsids = [user.crsid for user in session.execute(select(User)).scalars().all()]

        # Process tag updates
        for crsid in user_crsids:
            tags = request.form.getlist(f'tag_{crsid}[]')
            tags = [tag for tag in tags if tag.strip()]
            # Update the User table with the new tag values
            session.execute(
                update(User)
                .where(User.crsid == crsid)
                .values(tags=','.join(tags))
            )
        session.commit()
        return redirect(url_for('captains'))

    unique_tags = set()
    for user in users:
        if user.tags:
            tags = user.tags.split(',')
            for tag in tags:
                unique_tags.add(tag.strip())

    return(render_template(users=users,unique_tags=sorted(unique_tags),
            template_name_or_list='captains.html'))


@app.route('/commit_crews', methods=['POST'])
def commit_crews():
    for crsid, boat_list in request.form.items():
        if crsid.startswith('tag_'):
            crsid = crsid.split('_', 1)[1]
            tags = boat_list.split(',')  # Assuming boats are comma-separated

            # Fetch user by CRSId
            user = session.query(User).filter(User.crsid == crsid).first()
            if user:
                existing_tags = set(user.tags.split(',')) if user.tags else set()
                updated_tags = existing_tags.union(set(tags))
                user.tags = ','.join(updated_tags)
                session.commit()

    return redirect(url_for('captains'))

hours_of_day = range(6, 18)  # 6:00 to 17:00 (9 AM to 5 PM)

# Needs updating at very least
@app.route('/availability', methods=['GET', 'POST'])
def set_availabilities():
    crsid = auth_decorator.principal

    superuser = superuser_check(crsid, superusers)

    username = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

    # Export data from SQL into a format comprehensible by html-side JS interpreter
    def load_user_data(crsid):
        # Fetch all rows for the given crsid
        rows = session.execute(select(Daily)).scalars().all()

        # Initialize the dictionary
        state_dates = {}
        race_dates = {}
        event_dates = {}

        # Process each row
        for row in rows:
            date_str = row.date.strftime('%Y%m%d')  # Format date as YYYYMMDD
            races = row.races
            events = row.events

            if races:
                race_dates[date_str] = races

            if events:
                event_dates[date_str] = events

            user_data = json.loads(row.user_data) if row.user_data else {}

            # Check if the crsid is in user_data
            if crsid in user_data:
                state = user_data[crsid]

                # Initialize list for state if not already present
                if state not in state_dates:
                    state_dates[state] = []

                # Add the date to the list for the specific state
                state_dates[state].append(date_str)

        return state_dates, race_dates, event_dates

    existingData, raceDays, eventDays = load_user_data(crsid)

    context = {
        'existingData': existingData,
        'crsid': crsid,
        'username': username,
        'hours_of_day': hours_of_day,
        'existing': True,
        'superuser': superuser,
        'race_days': raceDays,
        'event_days': eventDays
    }

    now = datetime.now()
    year = now.year
    month = now.month
    current_month = int(month)

    selected_month = request.form.get('month', now.month)

    if 'refmonth' in request.args:
        selected_month=request.args.get('refmonth')

    # Convert the selected month to an integer
    selected_month = int(selected_month)

    # Get days in the month
    # Get days of the week (short format like "Mon", "Tue", etc.)
    days_of_week = calendar.weekheader(3).split()

    # Get a matrix where each list represents a week, and days outside the month are zero
    month_weeks = calendar.monthcalendar(year, selected_month)

    months = [(m, calendar.month_name[m]) for m in range(current_month, 13)]

    return render_template('calendar.html', **context, days_of_week=days_of_week,
                           month_weeks=month_weeks, months=months,
                           year=year,
                           month=selected_month)

@app.route('/submit_availability', methods=['POST'])
def submit_availability():
    crsid = auth_decorator.principal

    data = request.get_json()
    times = data.get('times', [])
    month = data.get('month')

    for time_entry in times:
        try:
            time, state = time_entry.split('|')

            date = datetime.strptime(time, '%Y%m%d').date()

            row = session.get(Daily, date)

            if row:
                if row.user_data:
                    user_data = json.loads(row.user_data)
                else:
                    user_data = {}

                # Update the user_data for the specific crsid
                user_data[crsid] = state

                row.user_data = json.dumps(user_data)
                session.merge(row)

            else:
                new_row = Daily(date=date, user_data=json.dumps({crsid: state}))
                session.add(new_row)

        except ValueError as e:
            print(f"Error processing time entry {time_entry}: {e}")
            continue

    # Commit all inserts to the database
    session.commit()

    return redirect(url_for('set_availabilities', refmonth=month))



@app.route('/planner', methods=['GET'])
def planner():
    crsid = auth_decorator.principal

    superuser = superuser_check(crsid, superusers)

    try:
        df = pd.read_json('availability.json', orient='records')
    except (ValueError, FileNotFoundError) as e:
        df = pd.DataFrame()
        print(f"error {e}")

    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    hours_of_day = [str(hour) for hour in range(6, 18)]  # Example hours

    # Apply the filter based on the parameter
    datadict = df.to_dict(orient='records')

    return render_template('planner.html', availabilities=datadict,
                           days_of_week=days_of_week, hours_of_day=hours_of_day, superuser=superuser)

# Needs updating for new availabilities system
@app.route('/delete_user', methods=['GET', 'POST'])
def delete_user():
    # Not implemented yet!

    crsid = auth_decorator.principal

    if 'crsid' in request.args:
        delid = request.args.get('crsid')
        if not crsid == delid or not superuser_check(crsid, superusers):
            return url_for(forbidden)
    else:
        delid = crsid

    if request.method == 'POST':
        deleteid = request.form.get("deleteid")

        if deleteid != delid:
            return(redirect(url_for("index")))

        try:
            shutil.rmtree(f'./data/{delid}')
        except:
            pass

        logid = session.execute(select(User.logbookid).where(User.crsid == delid)).scalar()

        if logid is not None:
            session.execute(delete(Workout).where(Workout.user_id == logid))
        session.execute(delete(User).where(User.crsid == delid))
        session.commit()

        return render_template_string('''
            All information for user {{delid}} deleted.

            <button type="submit" action="{{url_for("index")}}">Return Home</button>
        ''', delid=delid)

    return render_template_string('''
            <b> Are you sure you want to delete the user {{ delid }}? </b>

            Type the crsid in this box and submit to confirm user deletion.

            <b> All user information will be deleted! </b>

            <form method="POST" id="deleteConfirm" action="/delete_user?crsid={{ delid }}">
                <input type="text" name="deleteid" placeholder="CRSid"/>
                <button type="submit">Confirm</button>
            </form>
    ''', delid=delid)

@app.route('/captains/races', methods=['GET', 'POST'])
def set_races():
    crsid = auth_decorator.principal

    if crsid not in superusers:
        return redirect(url_for('forbidden', ref='captains'))

    if request.method == 'POST':
        crews = request.form.getlist(f'boat_[]')
        crews = [crew for crew in crews if crew.strip()] # will need better handling!

        add_event = {
            'name': request.form.get('name'),
            'date': request.form.get('date'),
            'type': request.form.get('type'),
            'crews': ','.join(crews)
        }

        new_event = Event(**add_event)
        session.merge(new_event)

        if request.form.get('type') == 'Race':
            into_date = Daily(date = request.form.get('date'), races = request.form.get('name'))
        else:
            into_date = Daily(date = request.form.get('date'), events = request.form.get('name'))

        session.merge(into_date)
        # Commit all inserts to the database
        session.commit()

    rows = session.execute(select(Event).order_by(asc(Event.date))).scalars().all()

    races_events = []

    for row in rows:
        races_events.append({
                'name': row.name,
                'date': row.date,
                'type': row.type,
                'crews': row.crews.split(',') if row.crews else []
            })

    return(render_template('races.html', races_events = races_events))

# boat builder!
@app.route('/captains/boats', methods=['GET', 'POST'])
def set_boats():
    crsid = auth_decorator.principal

    if crsid not in superusers:
        return redirect(url_for('forbidden', ref='captains'))

    boats = session.execute(select(Boat)).scalars().all()

    boats_list = []

    for row in boats:
        boats_list.append({
                'name': row.name,
                'tags': row.tags.split(',') if row.tags else [],
                'shell': row.shell,
                'active': row.active if row.active is not None else False,
            })

    return(render_template('boats.html', boats_list = boats_list))

@app.route('/captains/boats/edit', methods=['GET', 'POST'])
def edit_boat():
    crsid = auth_decorator.principal

    if crsid not in superusers:
        return redirect(url_for('forbidden', ref='captains'))

    if request.method == 'POST':
        # Handle the positions
        max_positions = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow']

        id_layout = {}

        for position in max_positions:
            if f'side-{position}' in request.form:
                _side_ = request.form.get(f'side-{position}')
                id_layout.update({position: _side_})

        boat_info = {
                'name': request.form.get('boat_name'),
                'crew_type': request.form.get('boat_type'),
                'shell': request.form.get('boat_shell'),
                'cox': request.form.get('seat-cox') if 'seat-cox' in request.form else None,
                'stroke': request.form.get('seat-stroke') if 'seat-stroke' in request.form else None,
                'seven': request.form.get('seat-seven') if 'seat-seven' in request.form else None,
                'six': request.form.get('seat-six') if 'seat-six' in request.form else None,
                'five': request.form.get('seat-five') if 'seat-five' in request.form else None,
                'four': request.form.get('seat-four') if 'seat-four' in request.form else None,
                'three': request.form.get('seat-three') if 'seat-three' in request.form else None,
                'two': request.form.get('seat-two') if 'seat-two' in request.form else None,
                'bow': request.form.get('seat-bow') if 'seat-bow' in request.form else None,
                'layout': json.dumps(id_layout),
            }

        new_boat = Boat(**boat_info)

        # Add (safely) to session
        session.merge(new_boat)

        # Commit all inserts to the database
        session.commit()

        return(redirect(url_for('set_boats')))

    if 'boat' in request.args:
        boat_name = request.args.get('boat')

        if boat_name != 'new':
            boats = session.execute(select(Boat).where(Boat.name == boat_name)).scalars().all()

            boats_list = {}

            for row in boats:
                boats_list.update({
                        'name': row.name,
                        'cox': row.cox if row.cox else None,
                        'stroke': row.stroke if row.stroke else None,
                        'seven': row.seven if row.seven else None,
                        'six': row.six if row.six else None,
                        'five': row.five if row.five else None,
                        'four': row.four if row.four else None,
                        'three': row.three if row.three else None,
                        'two': row.two if row.two else None,
                        'bow': row.bow if row.bow else None,
                        'tags': row.tags.split(',') if row.tags else [],
                        'crew_type': row.crew_type if row.crew_type else None,
                        'shell': row.shell if row.shell else None,
                    })
        else:
            boats_list = {'name': 'new',}

    user_crsids = {str(user.crsid):str(user.preferred_name+' '+user.last_name) for user in session.execute(select(User)).scalars().all()}

    return(render_template('editboat.html', boats_list = boats_list, user_list = user_crsids)) # temp

@app.route('/races')
def view_races():
    crsid = auth_decorator.principal
    return ("Not Implemented!")

def superuser_check(crsid, superusers):
    if crsid in superusers:
        return True
    else:
        return False

def format_seconds(seconds):
    # Calculate minutes, seconds, and tenths of seconds
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remainder = seconds % 60
    seconds_int = int(seconds_remainder)
    tenths = int((seconds_remainder - seconds_int) * 10)

    # Format the result as "minutes:seconds.tenths"
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds_int:02d}.{tenths}"
    elif minutes > 0:
        return f"{minutes}:{seconds_int:02d}.{tenths}"
    else:
        return f'{seconds_int}.{tenths}'

app.config.update(
    SESSION_COOKIE_SECURE=False,  # Ensure cookies are only sent over HTTPS
    SESSION_COOKIE_HTTPONLY=True, # Prevent JavaScript access to cookies
    SESSION_COOKIE_SAMESITE='Lax'  # CSRF protection
)
app.static_folder = 'static'

if __name__ == '__main__':
    app.run(port=21389,host='0.0.0.0', debug=True)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico')
