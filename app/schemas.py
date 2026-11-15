"""Pydantic schemas for data validation and API request/response contracts."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileCreate(BaseModel):
    elder_name: str = Field(..., min_length=2, max_length=100)
    elder_age: int | None = Field(None, ge=1, le=130)
    emergency_notes: str | None = Field(None, max_length=1000)
    elder_email: str | None = Field(None, max_length=120)
    caretaker_email: str | None = Field(None, max_length=120)
    family_email: str | None = Field(None, max_length=120)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    care_id: str
    elder_name: str
    elder_age: int | None = None
    emergency_notes: str | None = None
    caretaker_access_enabled: bool
    family_access_enabled: bool
    elder_email: str | None = None
    caretaker_email: str | None = None
    family_email: str | None = None


class LoginRequest(BaseModel):
    care_id: str = Field(..., min_length=3, max_length=20)
    passcode: str = Field(..., min_length=4, max_length=50)


class MedicationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    dosage: str = Field(..., min_length=1, max_length=80)
    times_per_day: int = Field(1, ge=1, le=10)
    schedule_times: str = Field(..., description="Comma separated HH:MM strings e.g. 08:00, 20:00")
    start_date: date
    end_date: date | None = None
    notes: str | None = Field(None, max_length=500)

    @field_validator("schedule_times")
    @classmethod
    def validate_schedule_times(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if not parts:
            raise ValueError("At least one scheduled time (HH:MM) is required.")
        for p in parts:
            if len(p) != 5 or p[2] != ":":
                raise ValueError(f"Time '{p}' must be in HH:MM 24-hour format.")
            hour, minute = p.split(":")
            if not (hour.isdigit() and minute.isdigit() and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError(f"Time '{p}' is not a valid 24-hour time.")
        return ", ".join(parts)


class MedicationCreate(MedicationBase):
    pass


class MedicationUpdate(MedicationBase):
    pass


class MedicationResponse(MedicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    plain_explanation: str | None = None
    created_at: datetime


class DoseLogCreate(BaseModel):
    medication_id: int
    dose_date: date
    scheduled_time: str
    status: str = Field(..., pattern="^(taken|skipped)$")
    notes: str | None = None


class DoseLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    medication_id: int
    dose_date: date
    scheduled_time: str
    status: str
    logged_at: datetime
    logged_by_role: str


class AppointmentBase(BaseModel):
    doctor_name: str = Field(..., min_length=2, max_length=120)
    appointment_date: datetime
    location: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=500)


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(AppointmentBase):
    pass


class AppointmentResponse(AppointmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    created_at: datetime


class AccessSettingsUpdate(BaseModel):
    caretaker_access_enabled: bool | None = None
    family_access_enabled: bool | None = None
    elder_email: str | None = None
    caretaker_email: str | None = None
    family_email: str | None = None
    regenerate_role: str | None = None  # "caretaker", "family", "elder"
