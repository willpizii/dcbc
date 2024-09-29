from sqlalchemy import Column, String, Date, Text
from dcbc.models.base import Base  # Import the shared Base
import uuid

class Event(Base):
    __tablename__ = 'events'

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    name = Column(String(255))

    date = Column(Date)

    type = Column(String(255))

    crews = Column(Text)
