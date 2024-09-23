import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON
from models.base import Base  # Import the shared Base

# Define the table structure with only the required columns
class Outing(Base):
    __tablename__ = 'outings'

    outing_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    date_time = Column(DateTime)
    boat_name = Column(String(255))

    set_crew = Column(JSON)

    shell = Column(String(255))

    subs = Column(String(255))
    coach = Column(String(255))
