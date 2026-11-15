"""Tests for Elder Access Settings, Contacts, and Emergency Directives."""


def test_elder_updates_contacts_and_notes(client, sample_profile, db_session, elder_auth_headers):
    """Test updating notification emails and emergency health directives."""
    res = client.post(
        "/settings/access/update-contacts",
        data={
            "elder_email": "updated.eleanor@example.com",
            "caretaker_email": "updated.nurse@example.com",
            "family_email": "updated.family@example.com",
            "emergency_notes": "Allergic to Penicillin and Sulfa. Blood type O positive.",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res.status_code == 303
    db_session.refresh(sample_profile)
    assert sample_profile.elder_email == "updated.eleanor@example.com"
    assert sample_profile.caretaker_email == "updated.nurse@example.com"
    assert "Sulfa" in sample_profile.emergency_notes


def test_caretaker_and_family_forbidden_from_settings(client, caretaker_auth_headers, family_auth_headers):
    """Test that only the Elder can access the /settings/access control panel."""
    # Caretaker should be forbidden (403)
    res_ct = client.get("/settings/access", headers=caretaker_auth_headers)
    assert res_ct.status_code == 403

    # Family should be forbidden (403)
    res_fam = client.get("/settings/access", headers=family_auth_headers)
    assert res_fam.status_code == 403
