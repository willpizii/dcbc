from sqlalchemy import Column, Integer, String, Boolean, Text
from dcbc.models.base import Base  # Import the shared Base

# Define the table structure with only the required columns
class User(Base):
    __tablename__ = 'users'

    crsid = Column(String(15), primary_key=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    logbookid = Column(Integer)
    color = Column(String(7))
    preferred_name = Column(String(255))

    bowside = Column(String(7))
    strokeside = Column(String(7))
    cox = Column(String(7))
    sculling = Column(String(7))
    years_rowing = Column(Integer)

    squad = Column(String(255))
    year = Column(String(3))
    subject= Column(String(255))

    logbook = Column(Boolean)

    tags = Column(Text)
    boats = Column(Text)
