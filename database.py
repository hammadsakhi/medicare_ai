
import os
from sqlalchemy import String, DateTime
from sqlalchemy.orm import mapped_column, Mapped
from datetime import datetime, time

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    String,
    Time,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

load_dotenv()

from config import get_setting

DATABASE_URL = get_setting("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check your project's .env file."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# Retained for compatibility with your existing database.
# Supabase will handle new user registration and authentication.
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id: Mapped[str] = mapped_column(
        String(10), primary_key=True
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    specialty: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    working_days: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    start_time: Mapped[time] = mapped_column(
        Time, nullable=False
    )
    end_time: Mapped[time] = mapped_column(
        Time, nullable=False
    )


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    patient_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    phone: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    doctor_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("doctors.doctor_id"),
        nullable=False,
    )

    appointment_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False
    )

    appointment_time: Mapped[time] = mapped_column(
        Time, nullable=False
    )

    reason: Mapped[str] = mapped_column(
        String(500), default="", nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default="confirmed", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Legacy local-user field, retained for compatibility.
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=True,
        index=True,
    )

    # Supabase authentication user ID for new appointments.
    # Nullable so older appointment records remain compatible.
    supabase_user_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index(
            "uq_confirmed_doctor_appointment_slot",
            "doctor_id",
            "appointment_date",
            "appointment_time",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )

class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    supabase_user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
def init_db():
    """Create tables, migrate ownership fields, and seed demo doctors."""

    Base.metadata.create_all(bind=engine)

    # Safely add the Supabase ownership column to an existing database.
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE appointments
                ADD COLUMN IF NOT EXISTS supabase_user_id VARCHAR(36)
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_appointments_supabase_user_id
                ON appointments (supabase_user_id)
                """
            )
        )

        # Remove the older full unique constraint, if it exists.
        connection.execute(
            text(
                """
                ALTER TABLE appointments
                DROP CONSTRAINT IF EXISTS uq_doctor_appointment_slot
                """
            )
        )

        # Prevent two confirmed bookings for the same slot while
        # allowing a cancelled slot to be booked again.
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_confirmed_doctor_appointment_slot
                ON appointments (
                    doctor_id,
                    appointment_date,
                    appointment_time
                )
                WHERE status = 'confirmed'
                """
            )
        )

    demo_doctors = [
        {
            "doctor_id": "DR001",
            "name": "Dr. Ayesha Khan",
            "specialty": "Cardiology",
            "working_days": "Mon-Fri",
            "start_time": time(9, 0),
            "end_time": time(15, 0),
        },
        {
            "doctor_id": "DR002",
            "name": "Dr. Hamza Ali",
            "specialty": "Dermatology",
            "working_days": "Mon-Sat",
            "start_time": time(10, 0),
            "end_time": time(17, 0),
        },
        {
            "doctor_id": "DR003",
            "name": "Dr. Sara Malik",
            "specialty": "Family Medicine",
            "working_days": "Mon-Sat",
            "start_time": time(9, 0),
            "end_time": time(16, 0),
        },
        {
            "doctor_id": "DR004",
            "name": "Dr. Usman Raza",
            "specialty": "Orthopedics",
            "working_days": "Mon-Fri",
            "start_time": time(11, 0),
            "end_time": time(18, 0),
        },
        {
            "doctor_id": "DR005",
            "name": "Dr. Zainab Noor",
            "specialty": "Pediatrics",
            "working_days": "Mon-Sat",
            "start_time": time(9, 0),
            "end_time": time(14, 0),
        },
    ]

    with SessionLocal() as session:
        for doctor_data in demo_doctors:
            existing = session.get(
                Doctor, doctor_data["doctor_id"]
            )

            if existing is None:
                session.add(Doctor(**doctor_data))

        session.commit()
