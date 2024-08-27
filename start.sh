. ~/Flaskenv/bin/activate

nohup gunicorn -w 4 -b 0.0.0.0:21389 app:app > gunicorn.log 2>&1 &


