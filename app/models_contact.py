from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    mobile = Column(String(20), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
