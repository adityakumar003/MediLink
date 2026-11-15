"""Authentication and role-security integration tests."""

import io
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import auth_headers


def _png_bytes(color: str = "blue") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_register_and_read_current_patient(
    client: TestClient,
    register_user,
) -> None:
    patient = register_user(age=32, gender="female")
    response = client.get("/auth/me", headers=auth_headers(patient))

    assert response.status_code == 200
    assert response.json()["role"] == "patient"


def test_login_and_reject_wrong_password(client: TestClient) -> None:
    email = f"login-{uuid4().hex}@example.com"
    registration = {
        "full_name": "Login Patient",
        "email": email,
        "password": "Pass123!",
        "role": "patient",
    }
    assert client.post("/auth/register", json=registration).status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email.upper(), "password": "Pass123!"},
    )
    wrong = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
    )

    assert login.status_code == 200
    assert login.json()["access_token"]
    assert wrong.status_code == 401


def test_public_registration_rejects_admin_role(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Unauthorized Admin",
            "email": f"admin-{uuid4().hex}@example.com",
            "password": "Pass123!",
            "role": "admin",
        },
    )

    assert response.status_code == 422


def test_profile_photo_upload_replace_and_remove(
    client: TestClient, register_user
) -> None:
    patient = register_user()
    headers = auth_headers(patient)

    assert client.get("/auth/me", headers=headers).json()["has_photo"] is False
    assert client.get("/auth/me/photo", headers=headers).status_code == 404

    upload = client.post(
        "/auth/profile-photo",
        headers=headers,
        files={"file": ("me.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    assert client.get("/auth/me", headers=headers).json()["has_photo"] is True

    photo = client.get("/auth/me/photo", headers=headers)
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"

    # Replace with a new photo, then remove it.
    replace = client.post(
        "/auth/profile-photo",
        headers=headers,
        files={"file": ("me2.png", _png_bytes("red"), "image/png")},
    )
    assert replace.status_code == 200

    removed = client.delete("/auth/profile-photo", headers=headers)
    assert removed.status_code == 200
    assert client.get("/auth/me", headers=headers).json()["has_photo"] is False
    assert client.get("/auth/me/photo", headers=headers).status_code == 404


def test_profile_photo_rejects_bad_files(client: TestClient, register_user) -> None:
    patient = register_user()
    headers = auth_headers(patient)

    bad_ext = client.post(
        "/auth/profile-photo",
        headers=headers,
        files={"file": ("me.txt", b"not an image", "text/plain")},
    )
    assert bad_ext.status_code == 400

    fake_img = client.post(
        "/auth/profile-photo",
        headers=headers,
        files={"file": ("fake.png", b"not really an image", "image/png")},
    )
    assert fake_img.status_code == 400

    assert client.post("/auth/profile-photo").status_code in (401, 403, 422)
