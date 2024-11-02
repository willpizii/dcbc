#!/bin/bash

# Activate the virtual environment
source /societies/downingboatclub/Prod/bin/activate

# Change to the parent directory
cd ..

# Start Gunicorn from the parent directory
python -m dcbc.daily_refresh

deactivate
