import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv
import uuid

load_dotenv()

DATABASE_URL = (
    f"mssql+pyodbc://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_SERVER')}:1433/{os.getenv('DB_NAME')}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "gpt"}
    id = Column(Integer, primary_key=True, autoincrement=True)  
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow) 

    threads = relationship("Thread", back_populates="user")

class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = {"schema": "gpt"}
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))  
    user_id = Column(Integer, ForeignKey("gpt.users.id"), nullable=False)         
    title = Column(String(100), default="New Chat")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete")

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"schema": "gpt"}
    id = Column(Integer, primary_key=True, autoincrement=True)                   
    thread_id = Column(String(36), ForeignKey("gpt.threads.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    thread = relationship("Thread", back_populates="messages")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()