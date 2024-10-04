import base64
import json
import os
import pickle
import random
import hashlib
import getpass
import io
import shutil
import copy

import numpy as np
import pandas as pd
import pyotp
import qrcode
from io import BytesIO
from datetime import datetime, time, timedelta
import calendar

import requests
from urllib.parse import urlencode, unquote

import flask
from flask import (Flask, redirect, Blueprint, request, jsonify,
                   render_template_string, send_file, url_for, g,
                   make_response, render_template, send_from_directory)
from flask import session as cookie_session

from flask_cors import CORS

from bokeh.io import output_file, show
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import (Range1d, LinearAxis, ColumnDataSource, HoverTool,
                          TapTool, CustomJS, FuncTickFormatter,
                          NumeralTickFormatter, CustomJSTickFormatter)

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

from werkzeug.middleware.proxy_fix import ProxyFix
from ucam_webauth.raven.flask_glue import AuthDecorator

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, select, exists, func, delete, update, asc, inspect, and_, or_, not_, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from dcbc.models.workout import Workout # Import from models.py
from dcbc.models.usersdb import User
from dcbc.models.boatsdb import Boat
from dcbc.models.dailydb import Daily
from dcbc.models.eventdb import Event
from dcbc.models.outings import Outing
from dcbc.models.base import Base

from dcbc.project.session import session, engine
from dcbc.project.auth_utils import load_secrets, setup_auth, load_users, get_decrypt_pass, auth_decorator, superuser_check
from dcbc.project.utils import format_seconds

from dcbc.routes.captains import captains_bp
from dcbc.routes.coaches import coach_bp

class R(flask.Request):
    trusted_hosts = {'wp280.user.srcf.net'}

app = Flask(__name__)
app.request_class = R

# Allow CORS for all subdomains of trusteddomain.com
CORS(app, resources={r"/*": {"origins": [
    r"http://wp280.user.srcf.net",
    r"https://wp280.user.srcf.net",
    r"http://*.concept2.com",
    r"https://*.concept2.com"
]}})

Base.metadata.create_all(engine)
session.commit()

# Comment these for live deployment
app.register_blueprint(captains_bp)
app.register_blueprint(coach_bp)

app.config['SERVER_NAME'] = 'wp280.user.srcf.net'
app.config['SESSION_COOKIE_NAME'] = 'cookie_session'

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# Change the before_request behaviour to vary per request
@app.before_request
def check_authentication():
    if request.path.startswith('/static/') or request.path.startswith('/coach') or request.path in ['/coach', '/favicon.ico', '/webhook']:
        return None  # Do not require a raven login for the above
    return auth_decorator.before_request()

@app.context_processor
def inject_superuser():
    crsid = auth_decorator.principal  # Get the principal (current user)
    is_superuser = superuser_check(crsid)  # Check if the user is a superuser
    return dict(superuser=is_superuser)

# Load secrets
secrets = load_secrets()

# Set up the authentication
CLIENT_ID, CLIENT_SECRET, decryptkey, datacipher = setup_auth(secrets)

# Load authorized users and superusers
authusers_file = 'dcbc/data/auth_users.txt'
superusers_file = 'dcbc/data/super_users.txt'
authusers, superusers = load_users(authusers_file, superusers_file)

# Pull in the app secret key
app.secret_key = secrets.get('secret_key')

# Callback URI after authorization on Concept2
REDIRECT_URI = 'https://wp280.user.srcf.net/callback'

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

# Stop gunicorn caching responses - which require dynamic updating!
@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        session.rollback()
    session.remove()

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

    file_path = f'dcbc/data/{crsid}'

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

    file_path = f'dcbc/data/{crsid}'

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
                "preferred_name": request.form.get('preferred_name') if request.form.get('preferred_name') else request.form.get('first_name'),
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
            userpath = f'dcbc/data/{crsid}'
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
            "preferred_name": request.form.get('preferred_name') if request.form.get('preferred_name') else request.form.get('first_name'),
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
        personal_data = personal_data))

@app.route('/home')
def index():

    crsid = auth_decorator.principal

    if not session.execute(select(exists().where(User.crsid == crsid))).scalar():
        return redirect(url_for('setup'))
    else:
        user = session.execute(select(User).where(User.crsid == crsid)).scalars().first()
        user_data = {column.name: getattr(user, column.name) for column in User.__table__.columns}

    file_path = f'dcbc/data/{crsid}'

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

    result = session.execute(select(User.boats).where(User.crsid == crsid)).scalar()

    # Safely handle the case where the result is None
    boats = result.split(",") if result else []

    your_boats = {} # Stores seat information for the boats you are a member of

    if boats:
        boat_columns = inspect(Boat).columns.keys()
        for boat in boats:
            if boat in ['', None]:
                continue
            boat_row = session.execute(select(Boat).where(Boat.name == boat)).scalar()
            if boat_row.active:
                for column in boat_columns:
                    if getattr(boat_row, column) == crsid:
                        your_boats.update({boat:column})
                        break

    today = datetime.now()
    next_week = today + timedelta(days=7)

    your_outings = session.execute(
        select(Outing).where(
            and_(
                Outing.date_time >= today.date(),  # Include events from today onwards
                Outing.date_time <= next_week,      # Up to one week from today
                or_(
                    Outing.boat_name.in_(boats),
                    func.find_in_set(crsid, Outing.subs)
                )
            )
        ).order_by(Outing.date_time.asc())
    ).scalars().all()

    your_outings = [
        outing for outing in your_outings
        if outing.set_crew is None or crsid not in json.loads(outing.set_crew)  # Check for None and key presence
    ]

    if logbook:
        logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()
        workouts = session.execute(
            select(Workout).where(Workout.user_id == logid).order_by(Workout.date.desc()).limit(5)
            ).scalars().all()
        workouts_dict = {index: copy.deepcopy(workout) for index, workout in enumerate(workouts)}

        best2k = session.execute(select(
            select(
                Workout.user_id,
                Workout.distance,
                Workout.time,
                Workout.workout_type,
                Workout.date
            )
            .where(
                Workout.user_id == logid,
                Workout.distance == 2000,
                Workout.workout_type == "FixedDistanceSplits"
            )
            .order_by(Workout.time.asc())
            .limit(1)
            .subquery()
        )).first()

        best5k = session.execute(select(
            select(
                Workout.user_id,
                Workout.distance,
                Workout.time,
                Workout.workout_type,
                Workout.date
            )
            .where(
                Workout.user_id == logid,
                Workout.distance == 5000,
                Workout.workout_type == "FixedDistanceSplits"
            )
            .order_by(Workout.time.asc())
            .limit(1)
            .subquery()
        )).first()

        best2k_copy = {key: value for key, value in best2k._mapping.items()}.copy() if best2k else None

        best5k_copy = {key: value for key, value in best5k._mapping.items()}.copy() if best5k else None

        if best2k_copy:
            best2k_copy['time'] = format_seconds(best2k_copy['time'] / 10)
            best2k_copy['date'] = best2k_copy['date'].date()

        if best5k_copy:
            best5k_copy['time'] = format_seconds(best5k_copy['time'] / 10)
            best5k_copy['date'] = best5k_copy['date'].date()

        for workout in workouts_dict.values():
            workout.split = format_seconds((workout.time / 10) / (workout.distance / 500))
            workout.time = format_seconds(workout.time / 10)

    else:
        workouts_dict = {}
        best2k_copy = {}
        best5k_copy = {}


    return(render_template(
        template_name_or_list='home.html', boats=your_boats, outings=your_outings,
        workouts_dict = workouts_dict, superuser=superuser, logbook=logbook,
        pb2k = best2k_copy, pb5k = best5k_copy))

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
    code = unquote(request.args.get('code')).strip()
    print(f"Received code: {repr(code)}")
    if not code:
        return 'No authorization code received.'

    token_params = {
        'grant_type': 'authorization_code',
        'code': f'{code}',
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }

    response = requests.post(TOKEN_URL, data=token_params)

    token_data = response.json()

    print(token_data)

    if 'access_token' not in token_data:
        return (f"Error - Expected access token, got invalid response")

    crsid = auth_decorator.principal

    userpath = f'dcbc/data/{crsid}'
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

    file_path = f'dcbc/data/{crsid}'

    token_path = f'{file_path}/token.txt'

    if os.path.exists(token_path):
        with open(token_path, 'rb') as file:
            encrypted_data = file.read()

        # Decrypt the data
        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

    else:
        return(url_for("setup"))

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
            }

            response = requests.get(data_url, headers=data_headers, params=data_params)

            dataresponse = response.json()

            len_recover = len(flatten_data(dataresponse))

            this_json = dataresponse.get('data')
            data_json += this_json

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

    file_path = f'dcbc/data/{crsid}'

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    query = select(Workout).where(Workout.user_id == logid, Workout.type == "rower")

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
        df=df, otherview=otherview, crsid=crsid,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

# Updated to SQL
@app.route('/data')
def data():
    crsid = auth_decorator.principal

    args = request.args

    if superuser_check(crsid, superusers):
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

    return render_template('data.html', data=subdf_dict, crsid=crsid,
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

    file_path = f'dcbc/data/{crsid}'

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
    crsids = session.execute(
                                select(User.crsid).where(
                                    not_(func.find_in_set('Inactive', User.tags))
                                )
                            ).scalars().all()
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

        query = select(Workout).where(Workout.user_id == logid, Workout.type == "rower")

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
        clubdf = [],
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
        clubdf = clubdf,
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

    file_path = f'dcbc/data/{crsid}'

    logid = session.execute(select(User.logbookid).where(User.crsid == crsid)).scalar()

    query = select(Workout).where(Workout.user_id == logid)

    # Use pandas to read the query result into a DataFrame
    df = pd.read_sql(query, engine)

    df['date'] = pd.to_datetime(df['date'])
    df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

    df['split'] = round((df['time'] / 10) / (df ['distance'] / 500),1)

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

    return redirect(url_for('captains.home'))

hours_of_day = range(6, 18)  # 6:00 to 17:00 (9 AM to 5 PM)

# Needs updating at very least
@app.route('/availability', methods=['GET', 'POST'])
def set_availabilities():
    crsid = auth_decorator.principal

    username = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

    # Export data from SQL into a format comprehensible by html-side JS interpreter
    def load_user_data(crsid):
        # Fetch all rows for the given crsid
        rows = session.execute(select(Daily)).scalars().all()

        # Initialize the dictionary
        state_dates = {}
        race_dates = {}
        event_dates = {}
        notes = {}

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
                state = user_data[crsid]['state']
                note = user_data[crsid]['notes']

                notes[date_str] = note

                # Initialize list for state if not already present
                if state not in state_dates:
                    state_dates[state] = []

                # Add the date to the list for the specific state
                state_dates[state].append(date_str)

        return state_dates, race_dates, event_dates, notes

    existingData, raceDays, eventDays, userNotes = load_user_data(crsid)

    user_tags = session.execute(select(User.tags).where(User.crsid == crsid)).scalars().first()

    user_tags = set() if user_tags is None else set(user_tags.split(','))

    if user_tags and not {'Captains', 'Coaches'}.intersection(user_tags):
        remove_races = []

        for race_date, race_name in raceDays.items():
            race_tags = set(session.execute(select(Event.crews).where(Event.name == race_name)).scalars().first().split(','))
            if not user_tags.intersection(race_tags):
                remove_races.append(race_date)

        for race_date in remove_races:
            del raceDays[race_date]

        remove_events = []

        for event_date, event_name in eventDays.items():
            event_tags = set(session.execute(select(Event.crews).where(Event.name == event_name)).scalars().first().split(','))
            if not user_tags.intersection(event_tags):
                remove_events.append(event_date)

        for event_date in remove_events:
            del eventDays[event_date]

    context = {
        'existingData': existingData,
        'crsid': crsid,
        'username': username,
        'hours_of_day': hours_of_day,
        'existing': True,
        'race_days': raceDays,
        'event_days': eventDays,
        'user_notes': userNotes
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
    notes = data.get('notes', {})

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
                if crsid not in user_data:
                    user_data[crsid] = {'state': state, 'notes': notes.get(time, None)}
                else:
                    # Update the 'state' field
                    user_data[crsid]['state'] = state
                    user_data[crsid]['notes'] = notes.get(time, None)

                row.user_data = json.dumps(user_data)
                session.merge(row)

            else:
                new_row = Daily(date=date, user_data=json.dumps({crsid: {'state': state, 'notes': notes.get(time, None)}}))
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
                           days_of_week=days_of_week, hours_of_day=hours_of_day)

# Needs updating for new availabilities system
@app.route('/delete_user', methods=['GET', 'POST'])
def delete_user():
    # Not implemented yet!

    crsid = auth_decorator.principal

    if 'crsid' in request.args:
        delid = request.args.get('crsid')
        if not crsid == delid or not superuser_check(crsid, superusers):
            return url_for("forbidden")
    else:
        delid = crsid

    if request.method == 'POST':
        deleteid = request.form.get("deleteid")

        if deleteid != delid:
            return(redirect(url_for("index")))

        try:
            shutil.rmtree(f'dcbc/data/{delid}')
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

@app.route('/races')
def view_races():
    crsid = auth_decorator.principal
    return ("Not Implemented!")

@app.route('/boat')
def view_boat():
    crsid = auth_decorator.principal
    boat = request.args.get('name', None)

    boats_list = {}

    if 'name' in request.args:
        boat_name = request.args.get('name')

        if boat_name != 'new':
            boats = session.execute(select(Boat).where(Boat.name == boat_name)).scalars().all()

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
                        'crew_type': row.crew_type if row.crew_type else None,
                        'shell': row.shell if row.shell else None,
                     })

    user_crsids = {str(user.crsid):str(user.preferred_name+' '+user.last_name) for user in session.execute(select(User)).scalars().all()}

    return(render_template('viewboat.html', boats_list = boats_list, user_list = user_crsids)) # temp

@app.route('/get_boat_info', methods=['POST'])
def get_boat_info():
    data = request.json
    boat_name = data.get('boat_name')

    boat = session.query(Boat).filter_by(name=boat_name).first()
    if boat:
        response_data = {
            'shell': boat.shell if boat.shell else None}

        user_crsids = {str(user.crsid): str(user.preferred_name + ' ' + user.last_name) for user in session.execute(select(User)).scalars().all()}

        # Add rowers to the response data using the user_crsids dictionary
        rower_positions = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow']

        for position in rower_positions:
            crsid = getattr(boat, position)
            response_data[position] = {
                'crsid': crsid,
                'name': user_crsids.get(crsid, None)
            } if crsid else None
        return jsonify(response_data)
    else:
        return jsonify({'error': 'Boat not found'}), 404

@app.route('/check_availability', methods=['POST'])
def check_availability():
    data = request.get_json()
    selected_date = data.get('date', '')

    if not selected_date:  # Check if the date is empty
        return jsonify({'error': 'Invalid date'}), 400  # Return an error response


    result = session.execute(select(Daily).where(Daily.date == selected_date)).first()

    lighting = pd.read_csv('dcbc/data/lightings.csv')

    lighting['Date'] = pd.to_datetime(lighting['Date'], format='%Y%m%d')

    lighting_up = lighting[lighting['Date'] == selected_date]['Friendly_Up'].iat[0]
    lighting_down = lighting[lighting['Date'] == selected_date]['Friendly_Down'].iat[0]

    if result:
        daily_record = result[0]  # Extract the Daily object from the result
        response_data = {
            'date': daily_record.date,
            'user_data': daily_record.user_data,
            'lighting_down': str(lighting_down), # Pass lighting times too
            'lighting_up': str(lighting_up)
        }
        return jsonify(response_data)  # Print the resulting row to the console
    else:
        return jsonify({'error': 'No availability found for this date'}), 404

@app.route('/find_crsid', methods=['POST'])
def find_crsid():
    data = request.get_json()
    full_name = data.get('name', '')

    # Split the full name into first and last names
    names = full_name.split()
    if len(names) < 2:
        return jsonify({'error': 'Please provide both first and last names.'}), 400

    first_name = names[0]
    last_name = ' '.join(names[1:])  # In case there are middle names

    # Implement your logic to find the CRSID based on the full name
    user = session.query(User).filter(
        User.preferred_name == first_name,
        User.last_name == last_name
    ).first()

    if user:
        return jsonify({'crsid': user.crsid})
    else:
        return jsonify({'error': 'CRSID not found'}), 404

@app.route('/outing')
def view_outing():

    out_id = request.args.get('id')

    if not out_id:
        return(redirect(url_for('home')))

    outing_info = session.execute(select(Outing).where(Outing.outing_id == out_id)).scalars().first()

    pos_seats = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow']

    outing_date = outing_info.date_time.date().strftime('%Y%m%d')

    lighting = pd.read_csv('dcbc/data/lightings.csv')

    lighting['Date'] = pd.to_datetime(lighting['Date'], format='%Y%m%d')

    filtered_lighting = lighting[lighting['Date'] == outing_date]

    lighting_up = filtered_lighting['Friendly_Up'].iat[0] if not filtered_lighting.empty else None
    lighting_down = filtered_lighting['Friendly_Down'].iat[0] if not filtered_lighting.empty else None

    if outing_info.scratch:
        subs_dict = {} # No subs in a scratch outing

        scratch_crew = json.loads(outing_info.set_crew)

        for seat, rower in scratch_crew.items():
            # Retrieve the user associated with the rower
            user = session.execute(select(User).where(User.crsid == rower)).scalars().first()

            # If user exists, update the seat with their formatted name
            if user:
                scratch_crew[seat] = f"{user.preferred_name} {user.last_name}"

        return(render_template("outing.html", outing = outing_info, crew = scratch_crew, subs = subs_dict, lup = lighting_up, ldown = lighting_down))

    outing_crew = session.execute(select(Boat).where(Boat.name == outing_info.boat_name)).scalars().first()

    crew_dict = {pos: getattr(outing_crew, pos) for pos in pos_seats if getattr(outing_crew, pos) is not None}

    if outing_info.set_crew is not None:
        to_sub = json.loads(outing_info.set_crew)

        subs_dict = {}

        for subbed, sub in to_sub.items():
            matched_seat = next((k for k, v in crew_dict.items() if v == subbed), None)

            if matched_seat:
                subs_dict[matched_seat] = sub

    else:
        subs_dict = None

    for seat, rower in crew_dict.items():
        # Retrieve the user associated with the rower
        user = session.execute(select(User).where(User.crsid == rower)).scalars().first()

        # If user exists, update the seat with their formatted name
        if user:
            crew_dict[seat] = f"{user.preferred_name} {user.last_name}"

    return(render_template("outing.html", outing = outing_info, crew = crew_dict, subs = subs_dict, lup = lighting_up, ldown = lighting_down))

@app.route('/outings', methods=['GET', 'POST'])
def outings():

    if 'weekof' in request.args:

        week_date = datetime.strptime(request.args.get('weekof'), '%Y-%m-%d').date()
        from_date = datetime.combine(week_date - timedelta(days=week_date.weekday()), datetime.min.time())

        # Calculate the end of the week (Sunday) at 23:59:59
        to_date = datetime.combine(from_date + timedelta(days=6), datetime.max.time())


    else:
        # Get today's date
        today = datetime.today()

        # Calculate the start of the week (Monday)
        from_date = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())

        # Calculate the end of the week (Sunday)
        to_date = datetime.combine(from_date + timedelta(days=6), datetime.max.time())

    crsid = auth_decorator.principal

    result = session.execute(select(User.boats).where(User.crsid == crsid)).scalar()

    # Safely handle the case where the result is None
    boats = result.split(",") if result else []

    user_name = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

    your_outings = session.execute(
        select(Outing).where(
            and_(
                Outing.date_time >= from_date,
                Outing.date_time <= to_date,
                or_(Outing.boat_name.in_(boats),
                    Outing.coach == user_name,
                    and_(Outing.scratch == True,
                         func.find_in_set(crsid, Outing.subs),
                        )
                    )
            )
        ).order_by(Outing.date_time.asc())
    ).scalars().all()

    sub_outings = session.execute(
        select(Outing).where(
            and_(
                Outing.date_time >= from_date,
                Outing.date_time <= to_date,
                func.find_in_set(crsid, Outing.subs),
                Outing.scratch == False
            )
        ).order_by(Outing.date_time.asc())
    ).scalars().all()

    other_outings = session.execute(
        select(Outing).where(
            and_(
                Outing.date_time >= from_date,
                Outing.date_time <= to_date,
                ~or_(Outing.boat_name.in_(boats),
                     Outing.coach == user_name)
            )
        ).order_by(Outing.date_time.asc())
    ).scalars().all()

    other_outings = [
        outing for outing in other_outings
        if outing.subs in ['', None] or crsid not in outing.subs.split(',')  # Check if subs is blank
    ]

    other_outings.extend([
        outing for outing in your_outings
        if outing.set_crew not in ['', None] and crsid in json.loads(outing.set_crew)
    ]) # Capture outings you are subbed out of

    your_outings = [
        outing for outing in your_outings
        if outing.set_crew in ['', None] or crsid not in json.loads(outing.set_crew)  # Check for None and key presence
    ]

    your_outings = [{
        "outing_id": outing.outing_id,
        "date_time": outing.date_time.isoformat(),
        "boat_name": outing.boat_name,
        "set_crew": outing.set_crew,
        "coach": outing.coach if outing.coach else 'No Coach',
        "time_type": outing.time_type if outing.time_type else 'ATBH',
        'notes': outing.notes if outing.notes else None
    } for outing in your_outings]

    sub_outings = [{
        "outing_id": outing.outing_id,
        "date_time": outing.date_time.isoformat(),
        "boat_name": outing.boat_name,
        "set_crew": outing.set_crew,
        "coach": outing.coach if outing.coach else 'No Coach',
        "time_type": outing.time_type if outing.time_type else 'ATBH',
        'notes': outing.notes if outing.notes else None
    } for outing in sub_outings]

    other_outings = [{
        "outing_id": outing.outing_id,
        "date_time": outing.date_time.isoformat(),
        "boat_name": outing.boat_name,
        "set_crew": outing.set_crew,
        "coach": outing.coach if outing.coach else 'No Coach',
        "time_type": outing.time_type if outing.time_type else 'ATBH',
        'notes': outing.notes if outing.notes else None
    } for outing in other_outings]

    races_events = session.execute(select(Event).where(
            and_(
                    Event.date >= from_date,
                    Event.date <= to_date
                )
        ).order_by(Event.date.asc())).scalars().all()

    races_events = [{
        "name": race_event.name,
        "date": race_event.date,
        "crews": race_event.crews,
        "type": race_event.type
    } for race_event in races_events]

    lighting = pd.read_csv('dcbc/data/lightings.csv')

    lighting['Date'] = pd.to_datetime(lighting['Date'], format='%Y%m%d')

    mask = (lighting['Date'] >= from_date) & (lighting['Date'] <= to_date)

    week_lighting = lighting[mask].to_dict(orient='records')

    return(render_template("outings.html", fromDate = from_date, toDate = to_date, crsid=crsid, user_outings = your_outings, other_outings=other_outings, sub_outings= sub_outings, races = races_events, lightings = week_lighting))

@app.route('/ergtable', methods=['GET', 'POST'])
def group_ergs():
    if request.method == 'POST':
        data = request.get_json()

        squad = data.get('squad')
        crew = data.get('crew')

        # Start with a base select statement
        stmt = select(User)

        # Add filters conditionally if the value is not 'all'
        conditions = []
        if squad != 'all':
            conditions.append(User.squad == squad)
        if crew != 'all':
            conditions.append(func.find_in_set(crew, User.boats))

        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')

        conditions.append(not_(func.find_in_set('Inactive', User.tags)))

        # Apply filters if any exist
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Execute the statement to get filtered users
        result = session.execute(stmt).scalars().all()

        log_names = {user.logbookid: str(user.preferred_name + ' ' + user.last_name) for user in result}

        logbook_ids = [user.logbookid for user in result]

        workouts = session.execute(select(Workout).where(and_(
                    Workout.user_id.in_(logbook_ids),
                    Workout.date.between(start_date, end_date)
                )).order_by(desc(Workout.date))).scalars().all()

        ergs = []

        for erg in workouts:
            erg_dict = {key: value for key, value in vars(erg).items() if not key.startswith('_')}
            erg_dict = {
                'user_id': log_names.get(erg_dict['user_id'], erg_dict['user_id']),
                'type': erg_dict['type'],
                'date': erg_dict['date'],
                'split': format_seconds(round((erg_dict['time'] / 10) / (erg_dict ['distance'] / 500),1)),
                'time': format_seconds(erg_dict['time']) if 'time' in erg_dict else '',
                'distance': erg_dict['distance'],
                'avghr': erg_dict['avghr'],
                'workout_type': erg_dict['workout_type'],
                'spm': erg_dict['spm'],
                'comments': erg_dict['comments'],
            }

            # Append this to the ergs list
            ergs.append(erg_dict)

        return(jsonify(ergs))

    unique_boats = set(row[0] for row in session.execute(select(Boat.name).where(Boat.active == True)).fetchall())

    crsid = auth_decorator.principal

    puser = session.execute(select(User).where(User.crsid == crsid)).scalar_one_or_none()

    if puser:
        # Check if the present-user has the 'Captains' tag
        is_captain = 'Captains' in puser.tags.split(',') if puser.tags else False

        if is_captain:
            squad_options = ['All', 'Womens', 'Mens']
        else:
            squad_options = [puser.squad] if puser.squad else ['All']  # Default to 'All' if no squad

    else:
        squad_options = ['All']  # Default if no puser is found

    return(render_template('ergtable.html', ergs=[], boats=sorted(unique_boats), squads=squad_options))

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
