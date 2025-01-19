#!/bin/bash

# Activate the virtual environment
source /societies/downingboatclub/Prod/bin/activate

source /societies/downingboatclub/pass.sh

# Change to the parent directory
cd ..

# Start Gunicorn from the parent directory
exec /societies/downingboatclub/Prod/bin/gunicorn -w 4 -b 0.0.0.0:21389 dcbc.app:app > dcbc/gunicorn.log 2>&1
