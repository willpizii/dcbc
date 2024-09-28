from sqlalchemy import Column, String, Date, Text
from dcbc.models.base import Base  # Import the shared Base

class Event(Base):
    __tablename__ = 'events'

    name = Column(String(255), primary_key=True)

    date = Column(Date)

    type = Column(String(255))

    crews = Column(Text)
