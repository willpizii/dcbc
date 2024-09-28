from sqlalchemy import Column, Integer, String, Date, Text, JSON
from dcbc.models.base import Base  # Import the shared Base

class Daily(Base):
    __tablename__ = 'daily'

    date = Column(Date, primary_key=True)

    user_data = Column(JSON)

    outings = Column(Text)
    races = Column(String(255))
    events = Column(String(255))
