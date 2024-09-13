from sqlalchemy import Column, Integer, String, Date, Text
from models.base import Base  # Import the shared Base

class Daily(Base):
    __tablename__ = 'daily'

    date = Column(Date, primary_key=True)

    out_of_cam = Column(Text)
    not_available = Column(Text)
    if_required = Column(Text)
    available = Column(Text)

    outings = Column(Text)
    races = Column(String(255))
    events = Column(String(255))
