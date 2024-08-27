import getpass
import os
import subprocess

# Prompt for the password
password = getpass.getpass("Enter your password: ")

# Export the password as an environment variable (if needed in the Flask app)
os.environ['FLASK_APP_PASSWORD'] = password

# Command to run the Flask app
command = ["python", "app.py"]

# Run the command using subprocess, redirecting output to a log file
with open("flask_app.log", "a") as log_file:
    subprocess.Popen(command, stdout=log_file, stderr=log_file)
