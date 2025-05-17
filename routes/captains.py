from flask import Blueprint, request, session, redirect, url_for, render_template, current_app, jsonify
from datetime import datetime, timedelta
import calendar
import json
from sqlalchemy import select, asc, and_, update, func, desc, not_

# Import necessary utilities and decorators
from dcbc.project.auth_utils import auth_decorator, superuser_check
from dcbc.models.usersdb import User
from dcbc.models.dailydb import Daily
from dcbc.models.hoursdb import Hourly
from dcbc.models.eventdb import Event
from dcbc.models.boatsdb import Boat
from dcbc.models.outings import Outing
from dcbc.models.workout import Workout
from dcbc.project.session import session  # Assuming your database session is set up in another file

from dcbc.project.utils import format_seconds


# Define the blueprint
captains_bp = Blueprint('captains', __name__, url_prefix='/captains')

@captains_bp.before_request
def check_superuser():
    crsid = auth_decorator.principal  # Get the CRSID from the auth decorator

    if not superuser_check(crsid):  # Check if the user is a superuser
        return redirect(url_for('forbidden', ref='captains'))  # Redirect if not

@captains_bp.route('/', methods=['GET', 'POST'])
def home():
    users = session.execute(select(User)).scalars().all()

    def format_tags(tags):
        if tags:
            return tags.replace(',', ' ').replace(' ', '-').lower()
        return ''

    current_app.jinja_env.filters['format_tags'] = format_tags

    if request.method == 'POST':
        # Retrieve all user CRSID values
        user_crsids = [user.crsid for user in session.execute(select(User)).scalars().all()]

        # Process tag updates
        for crsid in user_crsids:
            tags = request.form.getlist(f'tag_{crsid}[]')
            tags = [tag for tag in tags if tag.strip()]
            # Update the User table with the new tag values
            session.execute(
                update(User)
                .where(User.crsid == crsid)
                .values(tags=','.join(tags))
            )
        session.commit()

    unique_tags = set()
    for user in users:
        if user.tags:
            tags = user.tags.split(',')
            for tag in tags:
                unique_tags.add(tag.strip())

    return(render_template(users=users,unique_tags=sorted(unique_tags),
            template_name_or_list='captains.html'))


# Define the availability route
@captains_bp.route('/availability')
def availability():

    crsid = request.args.get('crsid')

    # Check if the user is a superuser
    superuser = superuser_check(crsid)

    # Get the username from the User table
    username = session.execute(select(User.preferred_name).where(User.crsid == crsid)).scalar() + ' ' + \
               session.execute(select(User.last_name).where(User.crsid == crsid)).scalar()

    # Helper function to load user data
    def load_user_data(crsid):
        rows = session.execute(select(Daily)).scalars().all()

        state_dates = {}
        race_dates = {}
        event_dates = {}
        notes = {}

        for row in rows:
            date_str = row.date.strftime('%Y%m%d')
            races = row.races
            events = row.events

            if races:
                race_dates[date_str] = races
            if events:
                event_dates[date_str] = events

            user_data = json.loads(row.user_data) if row.user_data else {}

            if crsid in user_data:
                state = user_data[crsid]['state']
                note = user_data[crsid]['notes']

                notes[date_str] = note

                if state not in state_dates:
                    state_dates[state] = []

                state_dates[state].append(date_str)

        return state_dates, race_dates, event_dates, notes

    # Fetch user data
    existingData, raceDays, eventDays, userNotes = load_user_data(crsid)

    # Set up context for the template
    context = {
        'existingData': existingData,
        'crsid': crsid,
        'username': username,
        'existing': True,
        'superuser': superuser,
        'race_days': raceDays,
        'event_days': eventDays,
        'user_notes': userNotes
    }

    now = datetime.now()
    year = now.year
    month = now.month
    current_month = int(month)

    # Handle form data and query params for month selection
    selected_month = request.form.get('month', now.month)

    if 'refmonth' in request.args:
        selected_month = request.args.get('refmonth')

    selected_month = int(selected_month)

    # Get days of the week and weeks in the selected month
    days_of_week = calendar.weekheader(3).split()
    month_weeks = calendar.monthcalendar(year, selected_month)

    months = [(m, calendar.month_name[m]) for m in range(current_month, 13)]

    # Render the calendar template
    return render_template('calendar.html', **context, days_of_week=days_of_week,
                           month_weeks=month_weeks, months=months,
                           year=year, month=selected_month)

@captains_bp.route('/races', methods=['GET', 'POST'])
def races():

    if request.method == 'POST':

        # Handle delete event
        if 'delete_event' in request.form:
            event_name_to_delete = request.form.get('delete_event')
            event_to_delete = session.execute(select(Event).filter(Event.event_id == event_name_to_delete)).scalar_one_or_none()
            if event_to_delete:
                # Remove the corresponding Daily entry
                daily_entry = session.execute(
                    select(Daily).filter(Daily.date == event_to_delete.date)
                ).scalar_one_or_none()

                if daily_entry:
                    # Assuming you want to clear the entry based on the event type
                    if event_to_delete.type == 'Race':
                        daily_entry.races = None  # or daily_entry.races.remove(event_to_delete.name) if you want to keep other races
                    else:
                        daily_entry.events = None  # or daily_entry.events.remove(event_to_delete.name)

                    session.merge(daily_entry)

                session.delete(event_to_delete)
                session.commit()
            return redirect('/captains/races')  # Redirect to refresh the page

        crews = request.form.getlist(f'boat_[]')
        crews = [crew for crew in crews if crew.strip()] # will need better handling!

        add_event = {
            'name': request.form.get('name'),
            'date': request.form.get('date'),
            'type': request.form.get('type'),
            'crews': ','.join(crews)
        }

        event_id = request.form.get('event_id')  # This will be None if creating a new event

        if event_id:  # Editing an existing event
            existing_event = session.execute(
                select(Event).where(Event.event_id == event_id)
            ).scalar_one_or_none()

            if existing_event:
                # If the event exists, find the related Daily entry
                daily_entry = session.execute(
                    select(Daily).where(Daily.date == existing_event.date)
                ).scalars().first()

                # Clear the date in Daily if it is changing
                if existing_event.date != add_event['date'] and daily_entry:
                    if existing_event.type == 'Race':
                        daily_entry.races = None  # Clear the races field
                    else:
                        daily_entry.events = None  # Clear the events field
                    session.merge(daily_entry)

                # Update the existing event's details
                existing_event.date = add_event['date']
                existing_event.type = add_event['type']
                existing_event.crews = ','.join(crews)  # Update crews
                session.merge(existing_event)

        else:  # Creating a new event
            new_event = Event(**add_event)
            session.merge(new_event)

        if request.form.get('type') == 'Race':
            into_date = Daily(date = request.form.get('date'), races = request.form.get('name'))
        else:
            into_date = Daily(date = request.form.get('date'), events = request.form.get('name'))

        session.merge(into_date)
        # Commit all inserts to the database
        session.commit()

    rows = session.execute(select(Event).order_by(asc(Event.date))).scalars().all()

    races_events = []

    for row in rows:
        races_events.append({
            'name': row.name,
            'date': row.date,
            'type': row.type,
            'crews': row.crews.split(',') if row.crews else [],
            'event_id': row.event_id  # Include event_id for deletion and editing
        })

    return(render_template('races.html', races_events = races_events))

# boat builder!
@captains_bp.route('/boats', methods=['GET', 'POST'])
def set_boats():
    boats = session.execute(select(Boat)).scalars().all()

    if request.method == 'POST' :
        merge_boats = {
                        'name': request.get_json().get('boat'),
                        'active': request.get_json().get('status') == 'True'
                        }
        merged_boats = Boat(**merge_boats)
        session.merge(merged_boats)
        session.commit()

        return ("OK", 200)

    boats_list = []

    for row in boats:
        boats_list.append({
                'name': row.name,
                'tags': row.tags.split(',') if row.tags else [],
                'shell': row.shell,
                'active': row.active if row.active is not None else False,
            })

    return(render_template('boats.html', boats_list = boats_list))

@captains_bp.route('/captains/boats/edit', methods=['GET', 'POST'])
def edit_boat():
    if request.method == 'POST':
        # Handle the positions
        max_positions = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow']

        id_layout = {}

        given_boat = request.form.get('boat_name')

        # Remove all instances of the boat passed from user boats field
        for user, user_boats in {str(user.crsid): (user.boats.split(',') if user.boats else [])
                                 for user in session.execute(select(User)).scalars().all()}.items():
            if given_boat in user_boats:
                user_boats.remove(given_boat)

                merge_boats = {
                                'crsid': user,
                                'boats': ','.join(user_boats) if user_boats is not [] else None
                                }
                merged_boats = User(**merge_boats)
                session.merge(merged_boats)

        session.commit()

        # Add the boat name back into the passed users
        for position in max_positions:
            if f'side-{position}' in request.form:
                _side_ = request.form.get(f'side-{position}')
                id_layout.update({position: _side_})

            if f'seat-{position}' in request.form:
                seat_crsid = request.form.get(f'seat-{position}')
                exist_boats = session.execute(select(User.boats).where(User.crsid == seat_crsid)).scalar()

                exist_boats = exist_boats.split(',') if exist_boats is not None else []

                if given_boat not in exist_boats:
                    exist_boats.append(given_boat)

                    merge_boats = {
                                    'crsid': seat_crsid,
                                    'boats': ','.join(exist_boats)
                                    }
                    merged_boats = User(**merge_boats)
                    session.merge(merged_boats)

        boat_info = {
                    'name': request.form.get('boat_name'),
                    'crew_type': request.form.get('boat_type'),
                    'shell': request.form.get('boat_shell'),
                    'cox': request.form.get('seat-cox') if 'seat-cox' in request.form else None,
                    'stroke': request.form.get('seat-stroke') if 'seat-stroke' in request.form else None,
                    'seven': request.form.get('seat-seven') if 'seat-seven' in request.form else None,
                    'six': request.form.get('seat-six') if 'seat-six' in request.form else None,
                    'five': request.form.get('seat-five') if 'seat-five' in request.form else None,
                    'four': request.form.get('seat-four') if 'seat-four' in request.form else None,
                    'three': request.form.get('seat-three') if 'seat-three' in request.form else None,
                    'two': request.form.get('seat-two') if 'seat-two' in request.form else None,
                    'bow': request.form.get('seat-bow') if 'seat-bow' in request.form else None,
                    'layout': json.dumps(id_layout),
                    'active': True
                }

        new_boat = Boat(**boat_info)

        # Add (safely) to session
        session.merge(new_boat)

        # Commit all inserts to the database
        session.commit()

        return(redirect(url_for('captains.set_boats')))

    if 'boat' in request.args:
        boat_name = request.args.get('boat')

        if boat_name != 'new':
            boats = session.execute(select(Boat).where(Boat.name == boat_name)).scalars().all()

            boats_list = {}

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
                        'tags': row.tags.split(',') if row.tags else [],
                        'crew_type': row.crew_type if row.crew_type else None,
                        'shell': row.shell if row.shell else None,
                    })
        else:
            boats_list = {'name': 'new',}

    user_crsids = {str(user.crsid):str(user.preferred_name+' '+user.last_name) for user in session.execute(select(User)).scalars().all()}

    return(render_template('editboat.html', boats_list = boats_list, user_list = user_crsids)) # temp

@captains_bp.route('/outings', methods=['GET', 'POST'])
def set_outings():
    if request.method == 'POST':
        delete_id = request.form.get('outing_id')

        delete_outing = session.execute(select(Outing).filter_by(outing_id=delete_id)).scalar_one_or_none()

        if delete_outing:
            session.delete(delete_outing)
            session.commit()

    from_date = datetime.strptime(request.args.get('from', datetime.today().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
    to_date = datetime.strptime(request.args.get('to', (datetime.today() + timedelta(days=7)).strftime('%Y-%m-%d')), '%Y-%m-%d').date()

    next_outings = session.execute(
            select(Outing).where(
                    and_(
                            Outing.date_time >= from_date,
                            Outing.date_time < to_date
                        )
                ).order_by(Outing.date_time.asc())
        ).scalars().all()

    return render_template('setoutings.html', outings = next_outings, from_date = from_date, to_date = to_date)

@captains_bp.route('/outings/edit', methods=['GET', 'POST'])
def edit_outing():
    if request.method == 'POST':
        # Handle POST request for editing or creating an outing
        outing_data = request.form  # Assuming you're sending JSON data

        new_outing = {
                'outing_id': outing_data.get('outing_id') if 'outing_id' in outing_data else None,
                'date_time': datetime.strptime(f"{outing_data.get('date')} {outing_data.get('time')}", "%Y-%m-%d %H:%M"),
                'boat_name': outing_data.get('boat_id'),
                'set_crew': {}, # Used to populate the crew list, for non-user subs
                'shell': outing_data.get('shell'),
                'subs': [], # Used to put into outings for the subs
                'coach': outing_data.get('coach'),
                'time_type': outing_data.get('timeType'),
                'notes': outing_data.get('notes') if 'notes' in outing_data else None,
                'scratch': False
            }

        # Iterate over the form data to process 'sub-' entries
        for key, value in outing_data.items():
            if key.startswith('sub-'):
                # Extract the parts after the hyphens
                parts = key.split('-')
                usr_key = parts[1] if len(parts) > 1 else None
                sub_key = parts[2] if len(parts) > 2 else None

                # Populate the set_crew dictionary
                if usr_key:
                    new_outing['set_crew'][usr_key] = value

                # Add sub_key to subs list if it's not empty
                if sub_key:
                    new_outing['subs'].append(sub_key)

        # Convert subs list to a comma-separated string if there are any subs
        if new_outing['subs']:
            new_outing['subs'] = ','.join(new_outing['subs'])
        else:
            new_outing['subs'] = None  # Ensure subs is None if empty

        if new_outing['set_crew']:
            new_outing['set_crew'] = json.dumps(new_outing['set_crew'])
        else:
            new_outing['set_crew'] = None  # Ensure set_crew is None if empty


        add_outing = Outing(**new_outing)

        session.merge(add_outing)
        session.commit()

        return redirect(url_for("captains.set_outings"))

    args = request.args

    if 'outing' not in args or args.get('outing') is None:
        return redirect(url_for("captains.edit_outing", outing="new"))

    if args.get('outing') == 'new':
        boat_options = [row[0] for row in session.execute(
            select(Boat.name).where(Boat.active == True)).fetchall()]

        return render_template('editouting.html', boat_options=boat_options, outing='new')

    # Handle case where outing is being edited
    outing_id = args.get('outing')
    outing = session.execute(select(Outing).where(Outing.outing_id==outing_id)).scalars().first()

    if outing.scratch:
        return redirect(url_for("captains.scratch_outing", outing=outing_id))

    if outing:
        boat_options = [row[0] for row in session.execute(
            select(Boat.name).where(Boat.active == True)).fetchall()]

        return render_template('editouting.html', boat_options=boat_options, outing=outing)

    return "Outing not found", 404

@captains_bp.route('/outings/scratch', methods=['GET', 'POST'])
def scratch_outing():
    if request.method == 'POST':
        # Handle the positions
        max_positions = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow']

        id_layout = {}

        outing_data = request.form
        outing_name = request.form.get('boat_id')

        subs = [request.form.get(seat) for seat in ['seat-cox', 'seat-stroke', 'seat-seven', 'seat-six', 'seat-five', 'seat-four', 'seat-three', 'seat-two', 'seat-bow'] if request.form.get(seat) is not None]
        crew = {seat.split('-')[-1]: request.form.get(seat)
                for seat in ['seat-cox', 'seat-stroke', 'seat-seven', 'seat-six', 'seat-five', 'seat-four', 'seat-three', 'seat-two', 'seat-bow'] if request.form.get(seat) is not None}

        new_outing = {
                'date_time': datetime.strptime(f"{outing_data.get('date')} {outing_data.get('time')}", "%Y-%m-%d %H:%M"),
                'boat_name': outing_name,
                'set_crew': json.dumps(crew),
                'shell': outing_data.get('shell'),
                'subs': ','.join(subs),
                'coach': outing_data.get('coach'),
                'time_type': outing_data.get('timeType'),
                'notes': outing_data.get('notes') if 'notes' in outing_data else None,
                'scratch': True
            }

        if 'outing_id' in outing_data:
            new_outing.update({'outing_id': outing_data.get('outing_id')})

        session.merge(Outing(**new_outing))

        session.commit()

        return(redirect(url_for('captains.set_outings')))

    args = request.args

    user_crsids = {str(user.crsid):str(user.preferred_name+' '+user.last_name) for user in session.execute(select(User)).scalars().all()}
    boats_list = {'name': 'new',}

    if 'outing' not in args or args.get('outing') is None:
        return redirect(url_for("captains.scratch_outing", outing="new"))

    if args.get('outing') == 'new':

        return render_template('scratchouting.html', user_list = user_crsids, boats_list=boats_list, outing='new')

    # Handle case where outing is being edited
    outing_id = args.get('outing')
    outing = session.execute(select(Outing).where(Outing.outing_id==outing_id)).scalars().first()

    scratch_crew = json.loads(outing.set_crew)

    boats_list = {}

    boats_list.update(scratch_crew)

    crew_types = {
        (1, 2): 'pair',
        (3, 4): 'coxless-four',
        5: 'coxed-four',
        range(6, 9): 'eight'
    }

    seat_count = len(scratch_crew)

    boats_list.update({
        'crew_type': next(
            (value for key, value in crew_types.items()
            if (isinstance(key, (tuple, range)) and seat_count in key)
            or (isinstance(key, int) and seat_count == key)
            ),
            None
        )
    })

    if outing:

        return render_template('scratchouting.html', outing=outing, user_list = user_crsids, boats_list=boats_list)

    return "Outing not found", 404

@captains_bp.route('/outings/land', methods=['GET', 'POST'])
def land_session():
    # TODO implement this!
    return None

@captains_bp.route('/group_calendar', methods=['GET', 'POST'])
def group_calendar():

    if request.method == 'POST':

        data = request.get_json()

        squad = data.get('squad')
        tag = data.get('tag')
        crew = data.get('crew')
        mode = data.get('mode')

        # Start with a base select statement
        stmt = select(User)

        # Add filters conditionally if the value is not 'all'
        conditions = []
        if squad != 'all':
            conditions.append(User.squad == squad)
        if tag != 'all':
            conditions.append(func.find_in_set(tag, User.tags))
        if crew != 'all':
            conditions.append(func.find_in_set(crew, User.boats))

        # Apply filters if any exist
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Execute the statement to get filtered users
        result = session.execute(stmt).scalars().all()

        # Build the users_list
        users_list = [{'crsid': user.crsid, 'name': str(user.preferred_name + ' ' + user.last_name)} for user in result]

        # Return both users_list and availability_data in the response
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')

        if not start_date or not end_date:  # Validate if both dates are provided
            return jsonify({'error': 'Invalid date range'}), 400

        if mode == 'daily':
            # Query to get all records within the date range
            results = session.execute(
                select(Daily).where(Daily.date.between(start_date, end_date))
            ).scalars().all()

            if results:
                # Prepare the response data by extracting date and user_data from each record
                availability_data = [
                    {'date': record.date, 'user_data': record.user_data} for record in results
                ]

                return jsonify({
                    'users_list': users_list,
                    'availability_data': availability_data
                })

        elif mode == 'hourly':
            results = session.execute(
                select(Hourly).where(Hourly.date.between(start_date, end_date))
            ).scalars().all()

            if results:
                # Prepare the response data by extracting date and user_data from each record
                availability_data = [
                    {'date': record.date, 'user_data': record.user_data} for record in results
                ]

                return jsonify({
                    'users_list': users_list,
                    'availability_data': availability_data
                })

        else:
            return jsonify({'error': 'No availability found for the given date range'}), 404

    users = session.execute(select(User)).scalars().all()
    unique_boats = set(row[0] for row in session.execute(select(Boat.name).where(Boat.active == True)).fetchall())

    unique_tags = set()

    for user in users:
        if user.tags:
            tags = user.tags.split(',')
            for tag in tags:
                unique_tags.add(tag.strip())

    return(render_template('groupcalendar.html', tags=sorted(unique_tags), boats=sorted(unique_boats), captainview=True))

