"""PDF upload, extraction, and analysis integration tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from tests.conftest import auth_headers
from tests.test_hf_space import MOCK_QWEN_OUTPUT


def test_upload_and_analyze_report(client: TestClient, register_user) -> None:
    patient = register_user()
    headers = auth_headers(patient)
    sample_pdf = Path(__file__).parents[2] / "test_report_aditya.pdf"

    with sample_pdf.open("rb") as report_file:
        upload = client.post(
            "/reports/upload",
            headers=headers,
            files={"file": (sample_pdf.name, report_file, "application/pdf")},
        )

    assert upload.status_code == 201, upload.text
    report_id = upload.json()["id"]

    analysis = client.post(f"/analysis/{report_id}", headers=headers)
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["status"] == "analyzed"

    result = client.get(f"/analysis/{report_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["summary"]
    assert result.json()["disease_risks"]["diabetes"]["level"] == "Insufficient Data"

    reports = client.get("/reports/list", headers=headers)
    assert reports.status_code == 200
    assert any(item["id"] == report_id and item["has_analysis"] for item in reports.json())


def test_upload_rejects_non_pdf(client: TestClient, register_user) -> None:
    patient = register_user()
    response = client.post(
        "/reports/upload",
        headers=auth_headers(patient),
        files={"file": ("notes.txt", b"not a PDF", "text/plain")},
    )

    assert response.status_code == 400


def test_upload_rejects_fake_pdf(client: TestClient, register_user) -> None:
    patient = register_user()
    response = client.post(
        "/reports/upload",
        headers=auth_headers(patient),
        files={"file": ("fake.pdf", b"not really a PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is not a valid PDF document."


def test_upload_and_analyze_image_report(client: TestClient, register_user) -> None:
    import io
    from unittest.mock import MagicMock, patch
    from PIL import Image

    patient = register_user()
    headers = auth_headers(patient)

    img = Image.new("RGB", (200, 100), color="white")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    upload = client.post(
        "/reports/upload",
        headers=headers,
        files={"file": ("lab_report.png", img_bytes.getvalue(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    report_id = upload.json()["id"]

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[10, 10], [100, 10], [100, 30], [10, 30]], ("Patient: Jane Doe", 0.99)],
            [[[10, 35], [200, 35], [200, 55], [10, 55]], ("Glucose: 110 mg/dL 70-100 High", 0.98)],
            [[[10, 60], [200, 60], [200, 80], [10, 80]], ("Hemoglobin: 13.8 g/dL 12.0-16.0 Normal", 0.97)],
        ]
    ]

    with patch("app.services.text_extraction_service.get_ocr_engine", return_value=mock_engine):
        analysis = client.post(f"/analysis/{report_id}", headers=headers)

    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["status"] == "analyzed"

    result = client.get(f"/analysis/{report_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["summary"]


def test_upload_rejects_fake_image(client: TestClient, register_user) -> None:
    patient = register_user()
    response = client.post(
        "/reports/upload",
        headers=auth_headers(patient),
        files={"file": ("fake.png", b"not really an image", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is not a valid image file."


def test_full_flow_through_mocked_hf_space(client: TestClient, register_user) -> None:
    """Tomorrow's path: upload -> extract -> HF Space -> validated stored result."""
    import fitz

    patient = register_user()
    headers = auth_headers(patient)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "COMPLETE BLOOD COUNT\nHemoglobin: 10.2 g/dL 12.0-15.5\nGlucose: 110 mg/dL 70-100\n",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    upload = client.post(
        "/reports/upload",
        headers=headers,
        files={"file": ("lab.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    report_id = upload.json()["id"]

    mock_client = MagicMock()
    mock_client.predict.return_value = MOCK_QWEN_OUTPUT
    with (
        patch("app.core.config.settings.AI_MODE", "hf_space"),
        patch("app.services.hf_space_service.Client", return_value=mock_client),
    ):
        analysis = client.post(f"/analysis/{report_id}", headers=headers)
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["status"] == "analyzed"

    result = client.get(f"/analysis/{report_id}", headers=headers)
    assert result.status_code == 200
    body = result.json()
    assert body["summary"]
    hb = next(p for p in body["parameters"] if "hemoglobin" in p["name"].lower())
    assert hb["value"] == 10.2
    assert hb["status"] == "Low"
    assert body["disease_risks"]["anemia"]["level"] == "Moderate Risk"

    # Re-requesting analysis must NOT call the Space again (quota hygiene).
    with (
        patch("app.core.config.settings.AI_MODE", "hf_space"),
        patch("app.services.hf_space_service.Client", return_value=mock_client) as mock_cls,
    ):
        repeat = client.post(f"/analysis/{report_id}", headers=headers)
    assert repeat.json()["status"] == "analyzed"
    mock_cls.assert_not_called()
