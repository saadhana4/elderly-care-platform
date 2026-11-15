"""SQLAlchemy Data Models for CareNest."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime.

    Returns:
        datetime: Current UTC datetime with timezone.utc.
    """
    return datetime.now(UTC)


class Profile(Base):
    """Healthcare Profile for an Elderly Person."""

    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    care_id = Column(String(20), unique=True, index=True, nullable=False)
    elder_name = Column(String(100), nullable=False)
    elder_age = Column(Integer, nullable=True)
    emergency_notes = Column(Text, nullable=True)

    # Secure Passcodes (Bcrypt Hashed)
    elder_passcode_hash = Column(String(255), nullable=False)
    caretaker_passcode_hash = Column(String(255), nullable=False)
    family_passcode_hash = Column(String(255), nullable=False)

    # Elder Access Control (Elder can approve or revoke access for other roles)
    caretaker_access_enabled = Column(Boolean, default=True, nullable=False)
    family_access_enabled = Column(Boolean, default=True, nullable=False)

    # Email contacts for automated alerts
    elder_email = Column(String(120), nullable=True)
    caretaker_email = Column(String(120), nullable=True)
    family_email = Column(String(120), nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    medications = relationship("Medication", back_populates="profile", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="profile", cascade="all, delete-orphan")
    dose_logs = relationship("DoseLog", back_populates="profile", cascade="all, delete-orphan")


class Medication(Base):
    """Medication schedule and prescription details."""

    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    dosage = Column(String(80), nullable=False)
    times_per_day = Column(Integer, nullable=False, default=1)
    schedule_times = Column(
        String(100), nullable=False, default="08:00"
    )  # Comma separated e.g. "08:00, 20:00"
    start_date = Column(Date, nullable=False, default=date.today)
    end_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    # Cached Gemini AI plain-language explanation (JSON string)
    plain_explanation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    profile = relationship("Profile", back_populates="medications")
    dose_logs = relationship("DoseLog", back_populates="medication", cascade="all, delete-orphan")


class DoseLog(Base):
    """Record of logged medication doses (Taken or Skipped)."""

    __tablename__ = "dose_logs"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    dose_date = Column(Date, nullable=False, index=True)
    scheduled_time = Column(String(10), nullable=False)  # HH:MM format
    status = Column(String(20), nullable=False)  # "taken" or "skipped"
    logged_at = Column(DateTime, default=utc_now, nullable=False)
    logged_by_role = Column(String(20), nullable=False)  # "elder" or "caretaker"
    notes = Column(Text, nullable=True)

    # Relationships
    profile = relationship("Profile", back_populates="dose_logs")
    medication = relationship("Medication", back_populates="dose_logs")


class Appointment(Base):
    """Medical appointments and clinic visits."""

    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    doctor_name = Column(String(120), nullable=False)
    appointment_date = Column(DateTime, nullable=False, index=True)
    location = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    profile = relationship("Profile", back_populates="appointments")
