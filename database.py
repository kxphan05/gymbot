from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.sql import func
import os

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)

    templates = relationship("Template", back_populates="user")
    logs = relationship("WorkoutLog", back_populates="user")


class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="templates")
    exercises = relationship(
        "TemplateExercise",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateExercise.order",
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="_user_template_uc"),)


class TemplateExercise(Base):
    __tablename__ = "template_exercises"
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    exercise_name = Column(String, nullable=False)
    default_sets = Column(Integer, default=3)
    default_weight = Column(Float, default=0.0)
    default_reps = Column(Integer, default=0)
    order = Column(Integer, default=0)

    template = relationship("Template", back_populates="exercises")


class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    template_name = Column(String, nullable=True)
    exercise_name = Column(String, nullable=False)
    sets = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)
    reps = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="logs")


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost/gymbot"
)

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
