"""Profile creation, passcode management, and authentication business logic."""

from sqlalchemy.orm import Session

from app.models import Profile
from app.security import (
    generate_care_id,
    generate_passcode,
    hash_passcode,
    verify_passcode,
)


def _generate_unique_care_id(db: Session) -> str:
    """Generate a unique care identifier not already present in the database."""
    care_id = generate_care_id()
    while db.query(Profile).filter(Profile.care_id == care_id).first():
        care_id = generate_care_id()
    return care_id


def create_care_profile(
    db: Session,
    elder_name: str,
    elder_age: int | None = None,
    emergency_notes: str | None = None,
    elder_email: str | None = None,
    caretaker_email: str | None = None,
    family_email: str | None = None,
) -> tuple[Profile, dict[str, str]]:
    """Create a new healthcare profile with 3 distinct hashed role passcodes.

    Args:
        db (Session): Database session.
        elder_name (str): Elder's full name.
        elder_age (int | None): Elder's age.
        emergency_notes (str | None): Emergency directives or allergies.
        elder_email (str | None): Elder's contact email.
        caretaker_email (str | None): Caretaker's contact email.
        family_email (str | None): Family member's contact email.

    Returns:
        tuple[Profile, dict[str, str]]: Created Profile and plaintext passcodes.
    """
    care_id = _generate_unique_care_id(db)
    elder_code = generate_passcode("elder")
    caretaker_code = generate_passcode("caretaker")
    family_code = generate_passcode("family")

    profile = Profile(
        care_id=care_id,
        elder_name=elder_name.strip(),
        elder_age=elder_age if (elder_age and elder_age > 0) else None,
        emergency_notes=emergency_notes.strip() if emergency_notes else None,
        elder_passcode_hash=hash_passcode(elder_code),
        caretaker_passcode_hash=hash_passcode(caretaker_code),
        family_passcode_hash=hash_passcode(family_code),
        caretaker_access_enabled=True,
        family_access_enabled=True,
        elder_email=elder_email.strip() if elder_email else None,
        caretaker_email=caretaker_email.strip() if caretaker_email else None,
        family_email=family_email.strip() if family_email else None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    plain_passcodes = {
        "elder": elder_code,
        "caretaker": caretaker_code,
        "family": family_code,
    }
    return profile, plain_passcodes


def _match_passcode_to_role(clean_passcode: str, profile: Profile) -> tuple[str | None, str | None]:
    """Test candidate passcode against role hashes and active permissions.

    Returns:
        tuple[Optional[str], Optional[str]]: (matched_role, error_message).
    """
    if verify_passcode(clean_passcode, profile.elder_passcode_hash):
        return "elder", None

    if verify_passcode(clean_passcode, profile.caretaker_passcode_hash):
        if not profile.caretaker_access_enabled:
            return "caretaker", "Caretaker access has been paused or revoked by the primary elder account."
        return "caretaker", None

    if verify_passcode(clean_passcode, profile.family_passcode_hash):
        if not profile.family_access_enabled:
            return "family", "Family view access has been paused or revoked by the primary elder account."
        return "family", None

    return None, "Invalid Care ID or Passcode. Please verify your credentials."


def authenticate_passcode(
    db: Session,
    care_id: str,
    passcode: str,
) -> tuple[Profile | None, str | None, str | None]:
    """Authenticate a candidate Care ID and Passcode against role hashes and access flags.

    Args:
        db (Session): Database session.
        care_id (str): Input Care Profile ID.
        passcode (str): Input role passcode.

    Returns:
        tuple[Profile | None, str | None, str | None]: (profile, role, error_message).
    """
    clean_care_id = care_id.strip().upper()
    clean_passcode = passcode.strip().upper()

    profile: Profile | None = db.query(Profile).filter(Profile.care_id == clean_care_id).first()
    if not profile:
        return None, None, "Invalid Care ID or Passcode. Please verify your credentials."

    role, err = _match_passcode_to_role(clean_passcode, profile)
    return profile, role, err


def regenerate_role_passcode(db: Session, profile: Profile, role: str) -> str:
    """Regenerate and hash a fresh passcode for a role, invalidating the previous one.

    Args:
        db (Session): Database session.
        profile (Profile): Target Profile instance.
        role (str): 'elder', 'caretaker', or 'family'.

    Returns:
        str: The newly generated plaintext passcode.
    """
    clean_role = role.strip().lower()
    new_code = generate_passcode(clean_role)
    new_hash = hash_passcode(new_code)

    if clean_role == "elder":
        profile.elder_passcode_hash = new_hash
    elif clean_role == "caretaker":
        profile.caretaker_passcode_hash = new_hash
    elif clean_role == "family":
        profile.family_passcode_hash = new_hash
    else:
        raise ValueError(f"Unknown role '{role}' for passcode regeneration.")

    db.commit()
    return new_code
