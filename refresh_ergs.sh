#!/bin/bash

# Activate the virtual environment
source /societies/downingboatclub/Prod/bin/activate

# Change to the parent directory
cd /societies/downingboatclub/public_html

source /societies/downingboatclub/pass.sh

# Start Gunicorn from the parent directory
python -m dcbc.daily_refresh

deactivate
