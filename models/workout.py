from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Define the table structure with only the required columns
class Workout(Base):
    __tablename__ = 'workouts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    date = Column(DateTime)
    distance = Column(Integer)
    type = Column(String(255))
    time = Column(Integer)
    spm = Column(Integer)
    avghr = Column(Integer)
    comments = Column(String(65535))
    stroke_data = Column(Boolean)
