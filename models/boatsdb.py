from sqlalchemy import Column, String, Text, Boolean
from dcbc.models.base import Base  # Import the shared Base

# Define the table structure with only the required columns
class Boat(Base):
    __tablename__ = 'boats'

    name = Column(String(255), primary_key=True)
    cox = Column(String(255))
    stroke = Column(String(255))
    seven = Column(String(255))
    six = Column(String(255))
    five = Column(String(255))
    four = Column(String(255))
    three = Column(String(255))
    two = Column(String(255))
    bow = Column(String(255))

    tags = Column(Text)
    layout = Column(Text)
    shell = Column(Text)
    crew_type = Column(Text)

    active = Column(Boolean)
