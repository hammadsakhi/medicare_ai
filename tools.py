
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from langchain_core.tools import tool

from database import SessionLocal, Doctor, Appointment


# =========================================================
# 1. VALIDATION HELPERS
# =========================================================

WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def parse_date(value: str) -> date:
    """Validate an appointment date."""
    try:
        requested_date = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use the date format YYYY-MM-DD.")

    if requested_date < date.today():
        raise ValueError("You cannot book an appointment in the past.")

    return requested_date


def parse_time(value: str) -> time:
    """Validate an appointment time in HH:MM format."""
    try:
        requested_time = time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use the time format HH:MM, such as 10:30.")

    if requested_time.tzinfo is not None:
        raise ValueError("Use local clinic time without a timezone.")

    if requested_time.second or requested_time.microsecond:
        raise ValueError("Choose a time in HH:MM format.")

    if requested_time.minute not in (0, 30):
        raise ValueError("Choose a slot starting on the hour or half-hour.")

    return requested_time


def require_user_id(supabase_user_id: str | None) -> str:
    """Require an authenticated user ID."""
    if not isinstance(supabase_user_id, str) or not supabase_user_id.strip():
        raise ValueError("You must be logged in to manage appointments.")

    return supabase_user_id.strip()


def get_doctor(session, doctor_id: str):
    """Find a doctor by ID."""
    if not isinstance(doctor_id, str) or not doctor_id.strip():
        raise ValueError("Please provide a doctor ID.")

    doctor = session.get(Doctor, doctor_id.strip().upper())

    if doctor is None:
        raise ValueError(
            f"Doctor {doctor_id} was not found. "
            "Use list_doctors to see available doctors."
        )

    return doctor


def is_working_day(doctor, requested_date: date) -> bool:
    """
    Support schedules such as:
    Mon-Fri, Monday-Friday, Mon-Sat,
    Mon,Tue,Wed,Thu,Fri, or Daily.

    Unknown schedule formats are rejected.
    """
    raw_days = str(getattr(doctor, "working_days", "") or "").strip().lower()

    if not raw_days:
        return False

    normalized = (
        raw_days.replace(" ", "")
        .replace("–", "-")
        .replace("—", "-")
        .replace(".", "")
    )

    if normalized in {
        "daily", "everyday", "allweek",
        "mon-sun", "monday-sunday",
    }:
        return True

    # Weekday ranges, such as Mon-Fri.
    if "-" in normalized and "," not in normalized:
        parts = normalized.split("-", 1)

        if len(parts) != 2:
            return False

        start_name, end_name = parts

        if start_name not in WEEKDAYS or end_name not in WEEKDAYS:
            return False

        start_day = WEEKDAYS[start_name]
        end_day = WEEKDAYS[end_name]
        day = requested_date.weekday()

        if start_day <= end_day:
            return start_day <= day <= end_day

        # Supports a range crossing Sunday, such as Fri-Mon.
        return day >= start_day or day <= end_day

    # Comma-separated days, such as Mon,Tue,Wed,Thu,Fri.
    parts = normalized.split(",")

    if not parts or any(part not in WEEKDAYS for part in parts):
        return False

    allowed_days = {WEEKDAYS[part] for part in parts}

    return requested_date.weekday() in allowed_days


def validate_doctor_slot(doctor, requested_date: date, requested_time: time):
    """Reject appointments outside the doctor's schedule."""
    if not is_working_day(doctor, requested_date):
        schedule = doctor.working_days or "not configured"

        raise ValueError(
            f"{doctor.name} does not work on "
            f"{requested_date.strftime('%A, %d %B %Y')}. "
            f"Recorded working days: {schedule}."
        )

    if not doctor.start_time <= requested_time < doctor.end_time:
        raise ValueError(
            f"The requested time is outside {doctor.name}'s clinic hours "
            f"({doctor.start_time.strftime('%H:%M')}-"
            f"{doctor.end_time.strftime('%H:%M')})."
        )


def get_booked_times(session, doctor_id: str, requested_date: date) -> set:
    """Get confirmed appointment times for a doctor on a given date."""
    return set(
        session.scalars(
            select(Appointment.appointment_time).where(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == requested_date,
                Appointment.status == "confirmed",
            )
        ).all()
    )


# =========================================================
# 2. DOCTOR DIRECTORY
# =========================================================

@tool
def list_doctors(specialty: str = "") -> dict:
    """List doctors, specialties, working days, and clinic hours."""
    with SessionLocal() as session:
        query = select(Doctor).order_by(Doctor.name)

        if specialty.strip():
            query = query.where(
                Doctor.specialty.ilike(f"%{specialty.strip()}%")
            )

        doctors = session.scalars(query).all()

        return {
            "doctors": [
                {
                    "doctor_id": doctor.doctor_id,
                    "name": doctor.name,
                    "specialty": doctor.specialty,
                    "working_days": doctor.working_days,
                    "start_time": doctor.start_time.strftime("%H:%M"),
                    "end_time": doctor.end_time.strftime("%H:%M"),
                }
                for doctor in doctors
            ]
        }


# =========================================================
# 3. CHECK AVAILABILITY
# =========================================================

@tool
def check_doctor_availability(
    doctor_id: str,
    appointment_date: str,
) -> dict:
    """Check available 30-minute slots for a doctor.
    Date format: YYYY-MM-DD."""
    requested_date = parse_date(appointment_date)
    now = datetime.now()

    with SessionLocal() as session:
        doctor = get_doctor(session, doctor_id)

        date_display = requested_date.strftime("%d %B %Y (%A)")

        if not is_working_day(doctor, requested_date):
            return {
                "success": True,
                "doctor_id": doctor.doctor_id,
                "doctor": doctor.name,
                "date": requested_date.isoformat(),
                "date_display": date_display,
                "available_slots": [],
                "message": (
                    f"{doctor.name} does not work on "
                    f"{requested_date.strftime('%A')}. "
                    f"Working days: {doctor.working_days or 'not configured'}."
                ),
            }

        booked_times = get_booked_times(
            session, doctor.doctor_id, requested_date
        )

        available_slots = []
        current = datetime.combine(requested_date, doctor.start_time)
        finish = datetime.combine(requested_date, doctor.end_time)

        # Only offer slots that can fit a full 30-minute appointment.
        while current + timedelta(minutes=30) <= finish:
            slot_time = current.time()

            if requested_date == now.date() and current <= now:
                current += timedelta(minutes=30)
                continue

            if slot_time not in booked_times:
                available_slots.append(current.strftime("%H:%M"))

            current += timedelta(minutes=30)

        return {
            "success": True,
            "doctor_id": doctor.doctor_id,
            "doctor": doctor.name,
            "specialty": doctor.specialty,
            "date": requested_date.isoformat(),
            "date_display": date_display,
            "working_days": doctor.working_days,
            "working_hours": (
                f"{doctor.start_time.strftime('%H:%M')} - "
                f"{doctor.end_time.strftime('%H:%M')}"
            ),
            "available_slots": available_slots,
            "message": (
                "Availability retrieved from the database."
                if available_slots
                else "No appointment slots are available for this date."
            ),
        }


# =========================================================
# 4. BOOK APPOINTMENT
# =========================================================

@tool
def book_appointment(
    patient_name: str,
    phone: str,
    doctor_id: str,
    appointment_date: str,
    appointment_time: str,
    reason: str = "",
    supabase_user_id: str = "",
) -> dict:
    """Book an appointment after patient confirmation.
    Revalidates the doctor's working day, clinic hours, date, time,
    and slot availability before saving."""
    owner_id = require_user_id(supabase_user_id)
    requested_date = parse_date(appointment_date)
    requested_time = parse_time(appointment_time)

    now = datetime.now()

    if (
        requested_date == now.date()
        and requested_time <= now.time().replace(tzinfo=None)
    ):
        raise ValueError(
            "This appointment time has already passed. "
            "Please choose a future time."
        )

    if not isinstance(patient_name, str):
        raise ValueError("Please provide the patient's full name.")

    patient_name = patient_name.strip()

    if not 2 <= len(patient_name) <= 100:
        raise ValueError(
            "Patient name must be between 2 and 100 characters."
        )

    if not isinstance(phone, str):
        raise ValueError("Please provide a valid contact phone number.")

    phone = phone.strip()
    digits = "".join(char for char in phone if char.isdigit())

    if not 7 <= len(digits) <= 15:
        raise ValueError("Please provide a valid contact phone number.")

    reason = (reason or "").strip()

    with SessionLocal() as session:
        doctor = get_doctor(session, doctor_id)

        # Validate the authoritative schedule before creating a record.
        validate_doctor_slot(doctor, requested_date, requested_time)

        booked_times = get_booked_times(
            session, doctor.doctor_id, requested_date
        )

        if requested_time in booked_times:
            raise ValueError(
                "That slot is already booked. "
                "Please check availability again."
            )

        appointment = Appointment(
            patient_name=patient_name,
            phone=phone,
            doctor_id=doctor.doctor_id,
            appointment_date=requested_date,
            appointment_time=requested_time,
            reason=reason[:500],
            status="confirmed",
            supabase_user_id=owner_id,
        )

        session.add(appointment)

        try:
            session.commit()
            session.refresh(appointment)
        except IntegrityError:
            session.rollback()
            raise ValueError(
                "That slot is already booked or conflicts with a database "
                "constraint. Please check availability again."
            )

        return {
            "success": True,
            "appointment_id": appointment.appointment_id,
            "status": appointment.status,
            "patient_name": appointment.patient_name,
            "doctor": doctor.name,
            "specialty": doctor.specialty,
            "date": requested_date.isoformat(),
            # Python computes the correct weekday from the actual date.
            "date_display": requested_date.strftime("%d %B %Y (%A)"),
            "time": requested_time.strftime("%H:%M"),
            "working_days": doctor.working_days,
            "message": "Appointment saved successfully.",
        }


# =========================================================
# 5. FIND AN APPOINTMENT
# =========================================================

@tool
def find_appointment(
    appointment_id: int,
    patient_phone: str,
    supabase_user_id: str = "",
) -> dict:
    """Find an appointment belonging to the authenticated user."""
    owner_id = require_user_id(supabase_user_id)

    with SessionLocal() as session:
        query = (
            select(Appointment, Doctor)
            .join(Doctor, Appointment.doctor_id == Doctor.doctor_id)
            .where(
                Appointment.appointment_id == appointment_id,
                Appointment.phone == patient_phone.strip(),
                Appointment.supabase_user_id == owner_id,
            )
        )

        result = session.execute(query).first()

        if result is None:
            return {
                "found": False,
                "message": "No matching appointment was found.",
            }

        appointment, doctor = result
        appointment_date = appointment.appointment_date

        return {
            "found": True,
            "appointment": {
                "appointment_id": appointment.appointment_id,
                "patient_name": appointment.patient_name,
                "doctor": doctor.name,
                "specialty": doctor.specialty,
                "date": appointment_date.isoformat(),
                "date_display": appointment_date.strftime(
                    "%d %B %Y (%A)"
                ),
                "time": appointment.appointment_time.strftime("%H:%M"),
                "status": appointment.status,
                "reason": appointment.reason,
            },
        }


# =========================================================
# 6. CANCEL AN APPOINTMENT
# =========================================================

@tool
def cancel_appointment(
    appointment_id: int,
    patient_phone: str,
    supabase_user_id: str = "",
) -> dict:
    """Cancel a confirmed appointment belonging to the authenticated user."""
    owner_id = require_user_id(supabase_user_id)

    with SessionLocal() as session:
        appointment = session.scalar(
            select(Appointment).where(
                Appointment.appointment_id == appointment_id,
                Appointment.phone == patient_phone.strip(),
                Appointment.supabase_user_id == owner_id,
                Appointment.status == "confirmed",
            )
        )

        if appointment is None:
            return {
                "success": False,
                "message": "No matching confirmed appointment was found.",
            }

        appointment.status = "cancelled"
        session.commit()

        return {
            "success": True,
            "appointment_id": appointment_id,
            "status": "cancelled",
            "message": "Appointment cancelled successfully.",
        }


# =========================================================
# 7. REGISTERED TOOLS
# =========================================================

TOOL_LIST = [
    list_doctors,
    check_doctor_availability,
    book_appointment,
    find_appointment,
    cancel_appointment,
]


def execute_tool(
    name: str,
    args: dict,
    supabase_user_id: str | None = None,
):
    """Execute an allowed tool and inject trusted account identity."""
    allowed_tools = {item.name: item for item in TOOL_LIST}

    if name not in allowed_tools:
        raise ValueError(f"Unknown tool: {name}")

    safe_args = dict(args)

    if name in {
        "book_appointment",
        "find_appointment",
        "cancel_appointment",
    }:
        safe_args["supabase_user_id"] = require_user_id(
            supabase_user_id
        )

    return allowed_tools[name].invoke(safe_args)
