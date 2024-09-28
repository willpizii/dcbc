#!/bin/bash

# Activate the virtual environment
source ~/Flaskenv/bin/activate

# Change to the parent directory
cd ..

# Start Gunicorn from the parent directory
nohup gunicorn -w 4 -b 0.0.0.0:21389 dcbc.app:app > dcbc/gunicorn.log 2>&1 &
