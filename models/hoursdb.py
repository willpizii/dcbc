from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from dcbc.models.base import Base  # Import the shared Base

class Hourly(Base):
    __tablename__ = 'hourly'

    date = Column(DateTime, primary_key=True)

    user_data = Column(JSON)
