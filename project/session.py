from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
import json
import os
from dcbc.models.base import Base

# Load secrets from your `.secrets` file
secrets = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.secrets')
if os.path.exists(secrets):
    with open(secrets, 'rb') as file:
        secrets_dict = json.load(file)
else:
    raise ValueError("secrets file not found!")

# Retrieve the database password
SQL_PASS = secrets_dict.get('sql_pass')

# Create the SQLAlchemy engine
engine = create_engine(
    f'mysql+pymysql://wp280:{SQL_PASS}@squirrel/wp280',
    pool_recycle=3600,
    poolclass=QueuePool
)

# Create session factory and scoped session
Session = sessionmaker(bind=engine)
session = scoped_session(Session)
