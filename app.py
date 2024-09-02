import base64
import json
import os
import pickle
import random
import hashlib
import getpass
import io

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pyotp
import qrcode
from io import BytesIO
from datetime import datetime, time, timedelta
import pyarrow as pa

import requests
from urllib.parse import urlencode

import flask
from flask import (Flask, redirect, Blueprint, request, session,
                   render_template_string, send_file, url_for,
                   make_response, render_template, send_from_directory)

from bokeh.io import output_file, show
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import (Range1d, LinearAxis, ColumnDataSource, HoverTool,
                          TapTool, CustomJS, FuncTickFormatter,
                          NumeralTickFormatter, CustomJSTickFormatter)

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

import cryptpandas as crp
from ucam_webauth.raven.flask_glue import AuthDecorator

class R(flask.Request):
    trusted_hosts = {'localhost', '127.0.0.1', 'wp280.user.srcf.net'}

app = Flask(__name__)
app.request_class = R

app.config['SERVER_NAME'] = 'wp280.user.srcf.net'

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# Initialize the AuthDecorator
auth_decorator = AuthDecorator(desc='DCBC Ergs')

# Attach the before_request handler to the Flask app
@app.before_request
def check_authentication():
    # Skip authentication for the /coach route
    if request.path.startswith('/static/') or request.path in ['/coach', '/coach/view', '/favicon.ico', '/webhook']:
        return None  # Allow the request to proceed without authentication
    # Otherwise, perform the authentication check
    return auth_decorator.before_request()

user = 0
welcome = 'User'

secrets = './.secrets'

if os.path.exists(secrets):
    with open(secrets, 'rb') as file:
        secrets_dict = json.load(file)

else:
    raise ValueError("secrets file not found!")

passhash = secrets_dict.get('passhash')

authusers_file = 'data/auth_users.txt'

with open(authusers_file, 'r') as file:
    authusers = [line.strip() for line in file.readlines()]

superusers_file = 'data/super_users.txt'

with open(superusers_file, 'r') as file:
    superusers = [line.strip() for line in file.readlines()]

app.secret_key = secrets_dict.get('secret_key')

decrypt_pass = os.environ.get('FLASK_APP_PASSWORD')

if decrypt_pass is None:
    raise ValueError("Environment variable FLASK_APP_PASSWORD is not set")

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

# Function to verify the input password against the stored hash
def verify_password(input_password, stored_hash):
    return create_hash(input_password) == stored_hash

if verify_password(decrypt_pass, passhash):
    print("Password is correct!")
else:
    raise ValueError("Password is incorrect! Aborting!")

def derive_key_from_password(password):
    # Use SHA-256 to hash the password and create a 256-bit key
    hashed_password = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed_password)

def decrypt_api_key(encrypted_data, password):
    key = derive_key_from_password(password)
    fernet = Fernet(key)
    decrypted_api_key = fernet.decrypt(encrypted_data).decode()
    return decrypted_api_key

# Replace these with your actual credentials
CLIENT_ID = secrets_dict.get('api_id')
CLIENT_SECRET = decrypt_api_key(secrets_dict.get('api_key'), decrypt_pass)

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

@app.route('/')
def default():
    resp = make_response(redirect(url_for('login')))
    return resp

@app.route('/sorry')
def sorry():
    return('Sorry, you don\'t have access to this page!')


@app.route('/login')
def login():
    crsid = auth_decorator.principal

    args = request.args
    if 'crsid' in args and crsid in superusers:
        crsid = args.get('crsid')

    if crsid not in authusers:
        return(redirect(url_for('sorry')))

    file_path = f'data/{crsid}'
    print(file_path)

    print(f"Checking path: {file_path}")

    # Check if the directory exists
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            print(f"Directory {file_path} exists.")
        else:
            print(f"{file_path} exists but is not a directory.")
    else:
        print(f"Directory {file_path} does not exist.")

    if os.path.exists(file_path):
        token_path = f'{file_path}/token.txt'

        users_file = './data/users.crypt'

        if os.path.exists(users_file):
            users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)
            print(users_data)
            if crsid in users_data['crsid'].values:
                user_data = users_data[users_data['crsid'] == crsid]
            else:
                authorized = False

                resp = (make_response(render_template(
                    template_name_or_list='welcome.html',
                    crsid = crsid, authorized=authorized)))

                return resp
        else:
            raise TypeError("Something has gone wrong - no users file found!")

        if user_data['Logbook'][0] == True:
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
                if response.status_code == 200:
                    user_data = response.json()['data']

                    info_file = f'{file_path}/user_info.txt'

                    user_data_json = json.dumps(user_data)

                    # Encrypt the JSON string
                    encrypted_data = datacipher.encrypt(user_data_json.encode())

                    # Write the encrypted data to the file
                    with open(info_file, 'wb') as file:  # Note 'wb' mode for binary writing
                        file.write(encrypted_data)
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

    else:
        authorized = False

        resp = (make_response(render_template(
            template_name_or_list='welcome.html',
            crsid = crsid, authorized=authorized)))

    return resp

@app.route('/setup', methods=['GET', 'POST'])
def setup():

    crsid = auth_decorator.principal

    if crsid not in authusers:
        return(redirect(url_for('sorry')))

    file_path = f'./data/{crsid}'

    args = request.args

    if 'no-logbook' in args:

        if request.method == 'POST':

            users_file = './data/users.crypt'

            # Append new row to DataFrame
            new_row = pd.DataFrame([{
                'crsid': crsid,
                'First Name': request.form.get('first_name'),
                'Last Name': request.form.get('last_name'),
                'color': request.form.get('color'),
                'Preferred Name': request.form.get('preferred_name'),
                'Squad': request.form.get('squad'),
                'Bowside': request.form.get('bowside'),
                'Strokeside': request.form.get('strokeside'),
                'Coxing': request.form.get('coxing'),
                'Sculling': request.form.get('sculling'),
                'Years Rowing': request.form.get('years_rowing'),
                'Year': request.form.get('year'),
                'Subject': request.form.get('subject'),
                'Logbook': False
            }])

            if os.path.exists(users_file):
                users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)

                # Append new row to DataFrame using pd.concat
                if crsid not in users_data['crsid'].values:
                    users_data = pd.concat([users_data, new_row], ignore_index=True)

                    # Save the updated DataFrame back to the CSV file
                    crp.to_encrypted(users_data, password = decrypt_pass, path=users_file)

                elif 'add-logbook' in args and crsid in users_data['crsid'].values: # adding a logbook after creation of a user
                    if 'logbook id' in users_data:
                        users_data[users_data['crsid'] == crsid]['logbook id'] = int(logid)
                    else:
                        users_data['logbook id'] = None
                        users_data[users_data['crsid'] == crsid]['logbook id'] = int(logid)
                    crp.to_encrypted(users_data, password = decrypt_pass, path=users_file)


            else:
                print(new_row)

                # Save the updated DataFrame back to the CSV file
                crp.to_encrypted(new_row, password = decrypt_pass, path=users_file)

            userpath = f'./data/{crsid}'
            if not os.path.exists(userpath):
                os.makedirs(userpath)

            return(redirect(url_for('index')))


        else:
            color = str("#"+''.join([random.choice('ABCDEF0123456789') for i in range(6)]))
            return(render_template(template_name_or_list='nologbook.html', crsid=crsid, color=color))


    else:

        token_path = f'{file_path}/token.txt'

        if not os.path.exists(token_path):
            return(redirect(url_for('login')))

        with open(token_path, 'rb') as file:
            encrypted_data = file.read()

        # Decrypt the data
        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())

        access_token = token_data['access_token']

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.get(USER_URL, headers=headers)  # Use GET to retrieve user data
        if response.status_code == 200:
            user_data = response.json()['data']

            info_file = f'./data/{crsid}/user_info.txt'

            user_data_json = json.dumps(user_data)

            # Encrypt the JSON string
            encrypted_data = datacipher.encrypt(user_data_json.encode())

            # Write the encrypted data to the file
            with open(info_file, 'wb') as file:  # Note 'wb' mode for binary writing
                file.write(encrypted_data)

            logid = user_data['id']
            first_name = user_data['first_name']
            last_name = user_data['last_name']
            color = str("#"+''.join([random.choice('ABCDEF0123456789') for i in range(6)]))

            # Load the users DataFrame
            users_file = './data/users.crypt'

            if os.path.exists(users_file):
                users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)

                # Append new row to DataFrame using pd.concat
                if crsid not in users_data['crsid'].values:
                    new_row = pd.DataFrame([{
                        'crsid': str(crsid),
                        'First Name': str(first_name),
                        'Last Name': str(last_name),
                        'logbook id': int(logid),
                        'color': str(color),
                        'Preferred Name': str(first_name),
                        'Logbook': True
                    }])

                    users_data = pd.concat([users_data, new_row], ignore_index=True)

                    # Save the updated DataFrame back to the CSV file
                    crp.to_encrypted(users_data, password = decrypt_pass, path=users_file)

                else: # adding a logbook after creation of a user
                    if users_data[users_data['crsid'] == crsid]['Logbook'][0] == False:
                        print(users_data[users_data['crsid'] == crsid]['Logbook'], logid)
                        users_data.loc[users_data['crsid'] == crsid, 'Logbook'] = True


                        if 'logbook id' in users_data:
                            users_data.loc[users_data['crsid'] == crsid, 'logbook id'] = int(logid)
                        else:
                            users_data['logbook id'] = None
                            users_data.loc[users_data['crsid'] == crsid, 'logbook id'] = int(logid)
                        crp.to_encrypted(users_data, password = decrypt_pass, path=users_file)
                        print(users_data[users_data['crsid'] == crsid]['Logbook'], logid, users_data[users_data['crsid'] == crsid]['logbook id'])


            else:
                print(new_row)

                # Save the updated DataFrame back to the CSV file
                crp.to_encrypted(new_row, password = decrypt_pass, path=users_file)


            return(redirect(url_for('user_settings')))
        else:
            return(redirect(url_for('authorize')))


@app.route('/home')
def index():

    crsid = auth_decorator.principal

    users = './data/users.crypt'

    if not os.path.exists(users):
        return redirect(url_for('setup'))

    users_data = crp.read_encrypted(password = decrypt_pass, path=users)

    if str(crsid) not in users_data['crsid'].values:
        return redirect(url_for('setup'))
    else:
        user_data = users_data[users_data['crsid'] == crsid]

    file_path = f'./data/{crsid}'

    if not os.path.exists(f'{file_path}/token.txt') and user_data['Logbook'][0] == True:
        return(redirect(url_for('authorize')))

    if user_data['Logbook'][0] == True:
        logbook = True
    else:
        logbook = False


    welcome = user_data['First Name'] + " " + user_data['Last Name']

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

    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in')

    file_path = f'{userpath}/workout_data.crypt'

    if os.path.exists(file_path):
        df = crp.read_encrypted(password = decrypt_pass, path=file_path)
        length_wd = len(df)

        resp = make_response(render_template_string('''
            <h1>Reload Data?</h1>
            <p>You have already previously loaded data, and you have {{ length_wd }} workouts loaded </p>
            <p><b>New workouts will (eventually, when I implement it) sync automatically!</b></p>
            <p><a href = "{{ url_for('load_all') }}"> I'm sure, load data</a></p>
            <p><a href = "{{ url_for('index') }}">Go Home</a></p>
        ''', length_wd = length_wd))

        return resp

    else:
        resp = make_response(redirect(url_for("load_all")))

        return resp

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
        "to": '2040-01-01',
        "type": "rower"
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

    # return redirect(url_for('index'))


    df = flatten_data(dataresponse)
    print(df)

    if len(df) == 50:
        len_recover = 50

        while len_recover != 1:
            old_set = df['date'].min()

            data_params = {
            "from": '2000-01-01',
            "to": old_set,
            "type": "rower",
            }

            response = requests.get(data_url, headers=data_headers, params=data_params)

            dataresponse = response.json()

            df = pd.concat([df, flatten_data(dataresponse)])
            df = df.drop_duplicates(subset='id')

            len_recover = len(flatten_data(dataresponse))

    csv_file_path = f'{file_path}/workout_data.crypt'

    if 'date' in df:
        df['date'] = pd.to_datetime(df['date'],format='ISO8601')
    else:
        return(render_template_string('''<h1>Your Logbook is empty!</h1>'''))

    df = df.sort_values('date')
    df = df.dropna(axis=1, how='all')

    for column in df.columns:
        try:
            # Attempt to create a Parquet-compatible PyArrow Table for this single column
            single_column_df = df[[column]]
            pa.Table.from_pandas(single_column_df)

        except pa.lib.ArrowNotImplementedError:
            # If it fails due to an ArrowNotImplementedError, drop the column
            print(f"Dropping column {column} due to failure in Parquet conversion.")
            df = df.drop(columns=[column])

    struct_columns = [col.split('.')[0] for col in df.columns if '.' in col]
    struct_columns = list(set(struct_columns))  # Remove duplicates

    # Check and drop problematic structs
    for struct_col in struct_columns:
        try:
            # Attempt to create a PyArrow Table for the entire struct
            struct_df = df[[col for col in df.columns if col.startswith(struct_col)]]
            pa.Table.from_pandas(struct_df)

        except pa.lib.ArrowNotImplementedError:
            # Drop all columns related to the problematic struct
            print(f"Dropping struct {struct_col} due to failure in Parquet conversion.")
            df = df.drop(columns=[col for col in df.columns if col.startswith(struct_col)])

    # Function to check if the 'heart_rate' field in 'workout.splits' is empty or malformed
    def clean_empties(value):
        if isinstance(value, dict):
            # Clean and filter the dictionary
            return {
                k: clean_empties(v)
                for k, v in value.items()
                if clean_empties(v)  # Keep only non-empty values
            }
        elif isinstance(value, list):
            # Clean and filter the list
            return [clean_empties(v) for v in value if clean_empties(v)]  # Keep only non-empty values
        return value

    # Usage example:
    df = df.applymap(clean_empties)
    print(df)

    crp.to_encrypted(df, path=csv_file_path, password=decrypt_pass)

    resp = make_response(redirect(url_for('setup')))

    return resp

@app.route('/webhook', methods=['POST'])
def webhook():
    # Attempt to parse the incoming JSON
    if request.is_json:
        webhook_data = request.get_json()

        # Print the type of event and the result payload
        event_type = webhook_data.get('type')
        result = webhook_data.get('result')

        if event_type == 'result-added':
            user_id = result.get('user_id')
            users = './data/users.crypt'

            if not os.path.exists(users):
                return redirect(url_for('setup'))

            users_data = crp.read_encrypted(password = decrypt_pass, path=users)

            if int(user_id) in users_data['logbook id'].values:
                user_data = users_data[users_data['logbook id'] == user_id].to_dict(orient='records')
                user_data = user_data[0]  # Get the first (and should be only) record

                # Now extract the crsid
                crsid = user_data['crsid']
            else:
                return "Invalid content type", 400

            print(crsid)

            # You can add further processing logic here
            # For example, you can store the result data in a database or trigger other actions

            df = pd.json_normalize(result)

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


            csv_file_path = f'data/{crsid}/workout_data.crypt'

            if 'date' in df:
                df['date'] = pd.to_datetime(df['date'],format='ISO8601')

            df = df.dropna(axis=1, how='all')

            # Function to check if the 'heart_rate' field in 'workout.splits' is empty or malformed
            def clean_empties(value):
                if isinstance(value, dict):
                    # Clean and filter the dictionary
                    return {
                        k: clean_empties(v)
                        for k, v in value.items()
                        if clean_empties(v)  # Keep only non-empty values
                    }
                elif isinstance(value, list):
                    # Clean and filter the list
                    return [clean_empties(v) for v in value if clean_empties(v)]  # Keep only non-empty values
                return value

            # Usage example:
            df = df.applymap(clean_empties)
            print(df)

            existingdf = crp.read_encrypted(path=csv_file_path, password=decrypt_pass)

            for column in existingdf.columns:
                if column not in df.columns:
                    df[column] = pd.NA

            # Reorder the columns in new_df to match the order in existingdf
            df = df[existingdf.columns]

            # Perform the merge operation
            merged_df = pd.concat([existingdf, df], ignore_index=True)

            crp.to_encrypted(merged_df, path=csv_file_path, password=decrypt_pass)

            return "Result successfully added and logged", 200

        elif event_type == 'result-updated':
            print(result)
            return "Not implemented", 200

        else:
            print(webhook_data)
            result_id = webhook_data.get('result_id')

            users_file = './data/users.crypt'
            users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)

            crsids = users_data['crsid'].values

            for crsid in crsids:
                user_path = f'./data/{crsid}'

                if not os.path.exists(f'{user_path}/workout_data.crypt'):
                    continue

                userdf = crp.read_encrypted(password = decrypt_pass, path=f'{user_path}/workout_data.crypt')

                if result_id in userdf['id'].values:
                    userdf = userdf[userdf['id'] != result_id]
                    crp.to_encrypted(userdf, password = decrypt_pass, path=f'{user_path}/workout_data.crypt')
                    print(f"Deleted result {result_id} from user {crsid}")
                    return f"Deleted result {result_id} from user {crsid}", 200

                else:
                    continue

            return "Result Not Found", 200
    else:
        print("Received non-JSON Payload")
        return "Invalid content type", 400


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

    users_file = './data/users.crypt'
    users = crp.read_encrypted(password = decrypt_pass, path=users_file)

    if not os.path.exists(file_path):
        if crsid not in users['crsid'].values and otherview:
            return(render_template(
                template_name_or_list='plot.html',
                script=[''],
                div=[f' <p>No specified user found!<a href={ url_for("index")}> Return to home </a></p>'],
                otherview=otherview, crsid=crsid,
                club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

        return(render_template(
            template_name_or_list='plot.html',
            script=[''],
            div=[f'No user found! <p><a href={ url_for("login")}> Return to login </a></p>'],
            otherview=otherview, crsid=crsid,
            club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

    if not os.path.exists(f'{file_path}/workout_data.crypt'):
        if crsid not in users['crsid'].values and otherview:
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

    df = crp.read_encrypted(path=f'{file_path}/workout_data.crypt',password=decrypt_pass)

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

    callback = CustomJS(args={'source': source, 'user':user, 'crsid':crsid}, code="""
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

    print (otherview)

    return(render_template(
        template_name_or_list='plot.html',
        script=[script1],
        div=[div1],
        df=df, otherview=otherview, crsid=crsid, superuser=superuser,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot')))

@app.route('/data')
def data():
    crsid = auth_decorator.principal

    args = request.args

    if superuser_check(crsid, superusers):
        if 'crsid' in args:
            crsid = args.get('crsid')

    file_path = f'./data/{crsid}'

    if not os.path.exists(file_path) or not os.path.exists(f'{file_path}/workout_data.crypt'):
        return redirect(url_for('login'))

    df = crp.read_encrypted(path=f'{file_path}/workout_data.crypt',password=decrypt_pass)

    df['date'] = pd.to_datetime(df['date'])
    df['distance'] = pd.to_numeric(df['distance'], errors='coerce')

    df['split'] = round((df['time'] / 10) / (df ['distance'] / 500),1)

    if 'from_date' in args and 'to_date' in args:
        from_date = args.get('from_date')
        to_date = args.get('to_date')

        # Filter the DataFrame
        df = df[(df['date'] >= from_date) & (df['date'] <= to_date)]

    else:
        from_date = df['date'].min()
        to_date = df['date'].max()

    df['split'] = df['split'].apply(format_seconds)

    totaldist = df['distance'].sum()
    totaltime = format_seconds((df['time'].sum())/10)

    df['time'] = (df['time']/10).apply(format_seconds)

    df = df.sort_values("date")

    max_select = ['id','date','distance','time','split','stroke_rate','workout_type','heart_rate.average','comments']
    select = []

    for item in max_select:
        if item in df.keys():
            select.append(item)

    subdf = df[select].copy()

    headers = ['id','Date','Distance','Time','Split / 500m','Stroke Rate','Type','Average HR','Comments']

    # Apply the function to each cell in the DataFrame
    if 'stroke_rate' in subdf:
        subdf['stroke_rate'] = subdf['stroke_rate'].apply(lambda x: int(x) if isinstance(x, (float, int)) and not pd.isna(x) else x)

    subdf.replace({np.nan: None, 'unknown': None}, inplace=True)

    subdf_dict = subdf.to_dict(orient='records')

    return render_template('data.html', data=subdf_dict,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'), headers=headers, totaldist=totaldist, totaltime=totaltime)

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

    info_file = f'./data/{crsid}/user_info.txt'

    if not os.path.exists(info_file):
        return(redirect(url_for('login')))

    # return (user_data)
    with open(info_file, 'rb') as file:
        encrypted_data = file.read()

    # Decrypt the data
    user_data = json.loads(datacipher.decrypt(encrypted_data).decode())

    logid = user_data['id']

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
        print("found stroke data")
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
    select = []

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

        # Append to `select` if the item exists in `res` and is not empty or invalid
        if value not in ['', np.nan, None, [], {}]:
            select.append(item)

    resdict = {k: res[k] if '.' not in k else res[k.split('.')[0]][k.split('.')[1]] for k in select}

    # Filter headers based on `select`
    filtered_headers = [headers_mapping[item] for item in select]

    return(render_template(
        template_name_or_list='workout.html',
        script=[script1],
        div=[div1],
        df=strokes,
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'),
        headers=filtered_headers, data=resdict))

@app.route('/club')
def club():

    users_file = './data/users.crypt'
    users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)

    crsids = users_data['crsid'].values
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
        user_path = f'./data/{crsid}'

        if not os.path.exists(f'{user_path}/workout_data.crypt'):
            continue

        userdf = crp.read_encrypted(password = decrypt_pass, path=f'{user_path}/workout_data.crypt')

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
        idcolor = users_data[users_data['crsid'] == crsid]['color'].values[0]
        idname = users_data[users_data['crsid'] == crsid]['First Name'].values[0] + ' ' + users_data[users_data['crsid'] == crsid]['Last Name'].values[0]

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

@app.route('/user_list')
def user_list():
    crsid = auth_decorator.principal
    if crsid not in superusers:
        return (redirect(url_for('forbidden', ref='user_list')))

    return render_template_string('''
        <h1>Select User</h1>
        <form method="get" action="{{ url_for('plot') }}">
            <label for="crsid">CRSid:</label>
            <input type="text" id="crsid" name="crsid" required>
            <input type="submit" value="View">
        </form>
    ''')

@app.route('/pbs')
def pbs():
    crsid = auth_decorator.principal

    file_path = f'./data/{crsid}'

    if not os.path.exists(file_path) or not os.path.exists(f'{file_path}/workout_data.crypt'):
        return redirect(url_for('login'))

    df = crp.read_encrypted(password = decrypt_pass, path=f'{file_path}/workout_data.crypt')

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
            session['authenticated'] = True

            user = get_coach(username, coaches)
            if not user['app_added']:
                user['app_added'] = True
                coaches[username] = user
                update_coaches(coaches)

            return(redirect(url_for('coachview', username=username)))
        else:
            return("2FA Failed!")

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
    if not session.get('authenticated'):
        return(render_template_string('''
            <h1>Session is not authenticated!</h1>
            <p><a href="{{ url_for('coach')}}"> Try logging in again! </a></p>
        '''))
    else:
        users_file = './data/users.crypt'
        users_data = crp.read_encrypted(password = decrypt_pass, path=users_file)

        crsids = users_data['crsid'].values
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
            user_path = f'./data/{crsid}'

            if not os.path.exists(f'{user_path}/workout_data.crypt'):
                continue

            userdf = crp.read_encrypted(password = decrypt_pass, path=f'{user_path}/workout_data.crypt')

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

        clubdf = pd.concat(dfs, axis=0, ignore_index=True)

        p1 = figure(height=350, sizing_mode='stretch_width', x_axis_type='datetime')

        for crsid in crsids:
            if f'{crsid}_date' not in clubdf:
                continue

            date=clubdf[f'{crsid}_date']
            distance=clubdf[f'{crsid}_distance'].cumsum()
            idcolor = users_data[users_data['crsid'] == crsid]['color'].values[0]
            idname = users_data[users_data['crsid'] == crsid]['First Name'].values[0] + ' ' + users_data[users_data['crsid'] == crsid]['Last Name'].values[0]

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

@app.route('/captains')
def captains():
    crsid = auth_decorator.principal

    if crsid not in superusers:
        return redirect(url_for('forbidden', ref='captains'))

    return(render_template(
            template_name_or_list='captains.html'))



@app.route('/user_settings', methods=['GET','POST'])
def user_settings():
    crsid = auth_decorator.principal

    superuser = superuser_check(crsid, superusers)

    users = './data/users.crypt'

    if not os.path.exists(users):
        return redirect(url_for('setup'))

    users_data = crp.read_encrypted(password = decrypt_pass, path=users)

    if str(crsid) not in users_data['crsid'].values:
        return redirect(url_for('setup'))

    personal_data = users_data.loc[users_data['crsid'] == crsid].to_dict('records')[0]

    keys = ['crsid', 'First Name', 'Last Name', 'logbook id', 'color', 'Preferred Name', 'Squad', 'Bowside', 'Strokeside', 'Coxing', 'Sculling', 'Years Rowing', 'Year', 'Subject']
    for key in keys:
        if key not in personal_data:
            personal_data[key] = ''
            users_data[key] = pd.NA

    if request.method == 'POST':
        new_data = {
            'crsid': crsid,
            'First Name': personal_data['First Name'],
            'Last Name': personal_data['Last Name'],
            'logbook id': personal_data['logbook id'],
            'color': personal_data['color'],
            'Preferred Name': request.form.get('preferred_name', personal_data['Preferred Name']),
            'Squad': request.form.get('squad', personal_data['Squad']),
            'Bowside': request.form.get('bowside', personal_data['Bowside']),
            'Strokeside': request.form.get('strokeside', personal_data['Strokeside']),
            'Coxing': request.form.get('coxing', personal_data['Coxing']),
            'Sculling': request.form.get('sculling', personal_data['Sculling']),
            'Years Rowing': request.form.get('years_rowing', personal_data['Years Rowing']),
            'Year': request.form.get('year', personal_data['Year']),
            'Subject': request.form.get('subject', personal_data['Subject']),
            'Logbook': personal_data['Logbook']
        }

        print(new_data)

        new_row = pd.DataFrame([new_data], index=users_data[users_data['crsid'] == crsid].index)

        # Update the existing row using DataFrame.update()
        users_data.update(new_row)

        personal_data = users_data.loc[users_data['crsid'] == crsid].to_dict('records')[0]

        crp.to_encrypted(users_data, password=decrypt_pass, path=users)

    return(render_template(
        template_name_or_list='user.html',
        club = url_for('club'), home = url_for('index'), data_url = url_for('data'), plot=url_for('plot'),
        authorize = url_for('authorize'), captains = url_for('captains'), superuser=superuser,
        personal_data = personal_data))

days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
hours_of_day = range(6, 18)  # 6:00 to 17:00 (9 AM to 5 PM)


@app.route('/availability', methods=['GET', 'POST'])
def set_availabilities():
    crsid = auth_decorator.principal

    superuser = superuser_check(crsid, superusers)

    if os.path.exists(f'./data/{crsid}/availability.json'):
        existing = True
        with open(f'./data/{crsid}/availability.json', 'r') as file:
            existingData = json.load(file)
    else:
        existing = False
        existingData = {}

    users = './data/users.crypt'
    users_data = crp.read_encrypted(password = decrypt_pass, path=users)

    if str(crsid) not in users_data['crsid'].values:
        print(crsid,'not found in',users_data['crsid'].values)
        return redirect(url_for('setup'))
    personal_data = users_data.loc[users_data['crsid'] == crsid].to_dict('records')[0]

    username = personal_data['Preferred Name'] +' '+ personal_data['Last Name']

    weeks = [1,2,3,4,5,6,7,8,9,10]
    selected_week = 1

    context = {
        'weeks': weeks,
        'selected_week': selected_week,
        'existingData': existingData,
        'crsid': crsid,
        'username': username,
        'days_of_week': days_of_week,
        'hours_of_day': hours_of_day,
        'existing': existing,
        'superuser': superuser
    }

    return render_template('availability.html', **context)

@app.route('/submit_availability', methods=['POST'])
def submit_availability():
    crsid = auth_decorator.principal

    data = request.get_json()
    name = data.get('name')
    times = data.get('times', [])
    week = data.get('week')

    # Organize times into different categories
    availability = {
        'available': [],
        'not-available': [],
        'if-needs-be': []
    }

    for time_entry in times:
        try:
            time, state = time_entry.split('|')
            if state in availability:
                availability[state].append(time)
        except ValueError:
            continue

    file_path = f'./data/{crsid}/availability.json'

    # Ensure the directory exists
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        user_data = {
            'weeks': {
                f'{week}': availability
            }
        }

        # Write the JSON data to the file
        with open(file_path, 'w') as f:
            json.dump(user_data, f, indent=4)

        return(redirect(url_for('set_availabilities')))

    else:
        with open(file_path, 'r') as f:
            avails = json.load(f)

        if week not in avails['weeks']:
            avails['weeks'][week] = {
                'available': [],
                'not-available': [],
                'if-needs-be': []
            }

        avails['weeks'][week] = availability

        with open(file_path, 'w') as f:
            json.dump(avails, f, indent=4)

        return redirect(url_for('set_availabilities'))



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
