from flask import Blueprint, request, redirect, url_for, render_template, current_app, render_template_string, g
from flask import session as cookie_session
from datetime import datetime, timedelta
import calendar
import json
import base64
import os
import pyotp
import qrcode
from io import BytesIO
from sqlalchemy import select, asc, and_, update, not_, func
import urllib.parse

import pandas as pd
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import ColumnDataSource, HoverTool, NumeralTickFormatter

# Import necessary utilities and decorators
from dcbc.project.auth_utils import auth_decorator, superuser_check
from dcbc.models.usersdb import User
from dcbc.models.dailydb import Daily
from dcbc.models.eventdb import Event
from dcbc.models.boatsdb import Boat
from dcbc.models.outings import Outing
from dcbc.models.workout import Workout

from dcbc.project.session import session, engine  # Assuming your database session is set up in another file
from dcbc.project.utils import format_seconds


# Define the blueprint
coach_bp = Blueprint('coaches', __name__, url_prefix='/coach')

@coach_bp.before_request
def before_request():
    # This makes the session available globally in templates
    g.cookie_session = cookie_session

    if request.endpoint == 'coaches.coach':
        return None  # Allow the request to continue without checking authentication

    if not g.cookie_session.get('authenticated'):
        return redirect(url_for('coaches.coach'))

@coach_bp.route('/')
def coach():
    coach_file = 'dcbc/data/coaches.txt'
    approved_file = 'dcbc/data/approved_coaches.txt'

    args = request.args
    username = args.get('username', None)

    if username:
        username = urllib.parse.unquote(username)

    notfound = args.get('notfound', False)
    code = args.get('tfa_code', False)

    if not username or notfound:
        return render_template_string(''' {% extends "coachbase.html" %} {% block content %} <div class="container mt-5">
            <h1>Welcome to the Coach Environment</h1>
            {% if notfound %}
                <h2>User not found, try again!</h2>
            {% endif %}
            <form method="get" action="{{ url_for('coaches.coach') }}">
                <label for="crsid">Username:</label>
                <input type="text" id="username" name="username" required>
                <input type="submit" value="View">
            </form> </div>{% endblock content %}
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
        return redirect(url_for('coaches.coach', username=username, notfound=True))

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

            return(redirect(url_for('coaches.view', username=username)))
        else:
            return(render_template_string('''  {% extends "coachbase.html" %} {% block content %}
                2FA Failed!

                <a href={{ url_for('coaches.coach') }}> Go back </a> {% endblock content %}
            '''))

    qr_code_base64 = generate_qr_code(username, coaches)
    qr_code_url = f'data:image/png;base64,{qr_code_base64}' if qr_code_base64 else None

    return(render_template_string('''  {% extends "coachbase.html" %} {% block content %}
            <!-- enable_2fa.html -->
            {% if username %}
                {% if not apped %}
                    <img src="{{ qrcode }}" alt="Scan this QR code with your Authenticator app">
                    <p>After scanning the QR code, enter the code generated by your authenticator app:</p>
                {% else %}
                    <p>Enter the code from your authenticator app:</p>
                {% endif %}
                <form method="get" action="{{ url_for('coaches.coach', username=username, code=tfa_code) }}">
                    <input type="text" name="tfa_code" required>
                    <input type="hidden" name="username" value="{{ username }}">
                    <button type="submit">Verify</button>
                </form>
            {% endif %}  {% endblock content %}
    ''', username=username, qrcode=qr_code_url, apped=apped))

@coach_bp.route('/outings', methods=['GET', 'POST'])
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


    all_outings = session.execute(
        select(Outing).where(
            and_(
                Outing.date_time >= from_date,
                Outing.date_time <= to_date
            )
        ).order_by(Outing.date_time.asc())
    ).scalars().all()

    sub_outings = []

    other_outings = []

    all_outings = [{
        "date_time": outing.date_time.isoformat(),
        "boat_name": outing.boat_name,
        "set_crew": outing.set_crew,
        "coach": outing.coach if outing.coach else 'No Coach',
        "time_type": outing.time_type if outing.time_type else 'ATBH',
        'notes': outing.notes if outing.notes else None
    } for outing in all_outings]


    return(render_template("coachoutings.html", fromDate = from_date, toDate = to_date, user_outings = all_outings, other_outings=other_outings, sub_outings= sub_outings))

@coach_bp.route('/view')
def view():
    if True:
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
            template_name_or_list='coachclub.html',
            script=[script1],
            div=[div1], totaldist = totaldist, totaltime = totaltime,
            clubdf = clubdf))
