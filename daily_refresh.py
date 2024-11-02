import os
import json
import requests
from sqlalchemy import create_engine, select
import pandas as pd
from datetime import datetime, timedelta

from dcbc.models.workout import Workout # Import from models.py
from dcbc.models.usersdb import User

from dcbc.project.session import session, engine
from dcbc.project.auth_utils import load_secrets, setup_auth, load_users, get_decrypt_pass, auth_decorator, superuser_check

secrets = load_secrets()

# Configuration
CLIENT_ID, CLIENT_SECRET, decryptkey, datacipher = setup_auth(secrets)
TOKEN_URL = 'https://log.concept2.com/oauth/access_token'

# Parameters (replace with actual workout ID for testing)
start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

# Query to pull workout IDs from workouts since the start_time
workout_datas = session.execute(
    select(Workout.id).where(Workout.date >= start_time)
).scalars().all()

for workoutid in workout_datas:
    # Fetch crsid from User table where logbookid matches the workoutid
    workout_data = session.execute(select(Workout).where(Workout.id == workoutid)).scalar_one()

    crsid_query = select(User.crsid).where(User.logbookid == workout_data.user_id)
    crsid = session.execute(crsid_query).scalar()

    if not crsid:
        raise ValueError("No user found with the provided workout ID.")

    # Paths
    file_path = f'dcbc/data/{crsid}'
    token_path = f'{file_path}/token.txt'
    data_url = f"https://log.concept2.com/api/users/{workout_data.user_id}/results/{workoutid}"

    # Check and load encrypted token
    if os.path.exists(token_path):
        with open(token_path, 'rb') as file:
            encrypted_data = file.read()
        token_data = json.loads(datacipher.decrypt(encrypted_data).decode())
        access_token = token_data['access_token']
        refresh_token = token_data['refresh_token']
    else:
        raise FileNotFoundError("Token file not found.")

    # Make request to API
    data_headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    response = requests.get(data_url, headers=data_headers)
    dataresponse = response.json()

    # Refresh token if necessary
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

        # Encrypt and save refreshed token
        encrypted_data = datacipher.encrypt(json.dumps(token_data).encode())
        with open(token_path, 'wb') as file:
            file.write(encrypted_data)

        access_token = token_data['access_token']
        data_headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        response = requests.get(data_url, headers=data_headers)
        dataresponse = response.json()

    # Extract and print workout data
    if 'data' in dataresponse:
        res = dataresponse['data']

        filtered_workout_data = {
            "id": res.get("id"),
            "user_id": res.get("user_id"),
            "date": res.get("date", None),  # Use None as a default
            "distance": res.get("distance", None),
            "type": res.get("type", None),
            "workout_type": res.get("workout_type", None),
            "time": res.get("time", None),
            "spm": res.get("stroke_rate", None),
            "avghr": res.get("heart_rate", {}).get("average", None),
            "comments": res.get("comments", None),    # If missing, default to None
            "stroke_data": res.get("stroke_data", False),
            "rest_time": res.get("rest_time", 0)
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

    else:
        print(f"Error - response status: {dataresponse.get('status_code', 'unknown')}, response: {dataresponse}")

session.close()
