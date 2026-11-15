"""Video consultation lifecycle, authorization, and LiveKit token tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from tests.conftest import auth_headers


def _connect_patient_and_doctor(
    client: TestClient,
    patient: dict,
    doctor: dict,
) -> None:
    doctor_headers = auth_headers(doctor)
    patient_headers = auth_headers(patient)

    profile = client.get("/doctors/profile", headers=doctor_headers)
    assert profile.status_code == 200, profile.text
    doctor_id = profile.json()["doctor_id"]

    request = client.post(
        "/patients/doctor-requests",
        headers=patient_headers,
        json={"doctor_id": doctor_id},
    )
    assert request.status_code == 201, request.text

    accepted = client.patch(
        f"/doctors/requests/{request.json()['request_id']}/respond",
        headers=doctor_headers,
        json={"accept": True},
    )
    assert accepted.status_code == 200, accepted.text


def test_video_consultation_full_lifecycle(
    client: TestClient,
    register_user,
) -> None:
    patient = register_user()
    doctor = register_user(role="doctor", specialization="Cardiology")
    patient_headers = auth_headers(patient)
    doctor_headers = auth_headers(doctor)
    _connect_patient_and_doctor(client, patient, doctor)

    created = client.post(
        "/video/consultations",
        headers=doctor_headers,
        json={"patient_id": patient["user"]["id"]},
    )
    assert created.status_code == 201, created.text
    consultation = created.json()
    assert consultation["status"] == "started"
    assert consultation["doctor_user_id"] == doctor["user"]["id"]
    assert consultation["patient_user_id"] == patient["user"]["id"]
    assert consultation["room_name"].startswith("medilink_")

    patient_view = client.get("/video/consultations", headers=patient_headers)
    assert patient_view.status_code == 200
    assert patient_view.json()[0]["status"] == "started"
    assert patient_view.json()[0]["can_join"] is True

    doctor_token = client.post(
        "/video/token",
        headers=doctor_headers,
        json={"consultation_id": consultation["id"]},
    )
    assert doctor_token.status_code == 200, doctor_token.text
    doctor_token_body = doctor_token.json()
    assert doctor_token_body["server_url"] == "wss://test.livekit.cloud"
    assert doctor_token_body["room_name"] == consultation["room_name"]
    assert doctor_token_body["role"] == "doctor"

    claims = jwt.decode(
        doctor_token_body["token"],
        settings.LIVEKIT_API_SECRET,
        algorithms=["HS256"],
    )
    assert claims["sub"] == doctor["user"]["id"]
    assert claims["video"]["room"] == consultation["room_name"]
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["canSubscribe"] is True
    assert claims["video"]["canPublishData"] is True

    patient_token = client.post(
        "/video/token",
        headers=patient_headers,
        json={"consultation_id": consultation["id"]},
    )
    assert patient_token.status_code == 200, patient_token.text
    patient_token_body = patient_token.json()
    assert patient_token_body["role"] == "patient"
    assert patient_token_body["consultation"]["status"] == "in_progress"

    in_progress = client.get(
        f"/video/consultations/{consultation['id']}",
        headers=doctor_headers,
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"

    patient_left = client.post(
        f"/video/consultations/{consultation['id']}/leave",
        headers=patient_headers,
    )
    assert patient_left.status_code == 200
    assert patient_left.json()["status"] == "in_progress"

    ended = client.post(
        f"/video/consultations/{consultation['id']}/end",
        headers=doctor_headers,
    )
    assert ended.status_code == 200
    assert ended.json()["status"] == "completed"

    completed_token = client.post(
        "/video/token",
        headers=patient_headers,
        json={"consultation_id": consultation["id"]},
    )
    assert completed_token.status_code == 409


def test_scheduled_consultation_requires_doctor_to_start(
    client: TestClient,
    register_user,
) -> None:
    patient = register_user()
    doctor = register_user(role="doctor")
    patient_headers = auth_headers(patient)
    doctor_headers = auth_headers(doctor)
    _connect_patient_and_doctor(client, patient, doctor)

    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    created = client.post(
        "/video/consultations",
        headers=doctor_headers,
        json={"patient_id": patient["user"]["id"], "scheduled_at": future},
    )
    assert created.status_code == 201, created.text
    consultation = created.json()
    assert consultation["status"] == "scheduled"
    assert consultation["can_start"] is True
    assert consultation["can_join"] is False

    too_early = client.post(
        "/video/token",
        headers=patient_headers,
        json={"consultation_id": consultation["id"]},
    )
    assert too_early.status_code == 409
    assert "not started" in too_early.json()["detail"].lower()

    started = client.post(
        f"/video/consultations/{consultation['id']}/start",
        headers=doctor_headers,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "started"

    patient_token = client.post(
        "/video/token",
        headers=patient_headers,
        json={"consultation_id": consultation["id"]},
    )
    assert patient_token.status_code == 200, patient_token.text
    assert patient_token.json()["consultation"]["status"] == "in_progress"


def test_video_consultation_authorization(
    client: TestClient,
    register_user,
) -> None:
    patient = register_user()
    doctor = register_user(role="doctor")
    other_doctor = register_user(role="doctor")
    patient_headers = auth_headers(patient)
    doctor_headers = auth_headers(doctor)
    other_doctor_headers = auth_headers(other_doctor)

    unconnected = client.post(
        "/video/consultations",
        headers=other_doctor_headers,
        json={"patient_id": patient["user"]["id"]},
    )
    assert unconnected.status_code == 403

    _connect_patient_and_doctor(client, patient, doctor)
    created = client.post(
        "/video/consultations",
        headers=doctor_headers,
        json={"patient_id": patient["user"]["id"]},
    )
    assert created.status_code == 201
    consultation_id = created.json()["id"]

    patient_cannot_start = client.post(
        "/video/consultations",
        headers=patient_headers,
        json={"patient_id": patient["user"]["id"]},
    )
    assert patient_cannot_start.status_code == 403

    unrelated_doctor = client.post(
        "/video/token",
        headers=other_doctor_headers,
        json={"consultation_id": consultation_id},
    )
    assert unrelated_doctor.status_code == 403

    patient_cannot_end = client.post(
        f"/video/consultations/{consultation_id}/end",
        headers=patient_headers,
    )
    assert patient_cannot_end.status_code == 403

    invalid_id = client.post(
        "/video/token",
        headers=doctor_headers,
        json={"consultation_id": "not-a-valid-object-id"},
    )
    assert invalid_id.status_code == 404


def test_video_token_returns_service_unavailable_without_configuration(
    client: TestClient,
    register_user,
    monkeypatch,
) -> None:
    patient = register_user()
    doctor = register_user(role="doctor")
    doctor_headers = auth_headers(doctor)
    _connect_patient_and_doctor(client, patient, doctor)

    created = client.post(
        "/video/consultations",
        headers=doctor_headers,
        json={"patient_id": patient["user"]["id"]},
    )
    assert created.status_code == 201
    consultation_id = created.json()["id"]

    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "")
    response = client.post(
        "/video/token",
        headers=doctor_headers,
        json={"consultation_id": consultation_id},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_scheduled_consultation_can_be_cancelled(
    client: TestClient,
    register_user,
) -> None:
    patient = register_user()
    doctor = register_user(role="doctor")
    patient_headers = auth_headers(patient)
    doctor_headers = auth_headers(doctor)
    _connect_patient_and_doctor(client, patient, doctor)

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    created = client.post(
        "/video/consultations",
        headers=doctor_headers,
        json={"patient_id": patient["user"]["id"], "scheduled_at": future},
    )
    assert created.status_code == 201, created.text
    consultation_id = created.json()["id"]

    cancelled = client.post(
        f"/video/consultations/{consultation_id}/cancel",
        headers=patient_headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    cannot_start = client.post(
        f"/video/consultations/{consultation_id}/start",
        headers=doctor_headers,
    )
    assert cannot_start.status_code == 409

    cannot_join = client.post(
        "/video/token",
        headers=patient_headers,
        json={"consultation_id": consultation_id},
    )
    assert cannot_join.status_code == 409
