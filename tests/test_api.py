from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base


@pytest.fixture
def client(tmp_path: Path):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_sessions = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    app = main.create_app(test_engine, test_sessions, tmp_path / "certificates")
    with TestClient(app) as test_client:
        yield test_client
    test_engine.dispose()


def request_body(recipients: list[object]) -> dict:
    return {"event_name": "Python Foundations", "issuer": "Example Academy", "recipients": recipients}


def test_create_job_generates_certificates_and_reports_progress(client: TestClient):
    response = client.post("/jobs", json=request_body([{"name": "Ada Lovelace"}, {"name": "Grace Hopper"}]))

    assert response.status_code == 202
    job = client.get(response.json()["status_url"])
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["total"] == 2
    assert job.json()["completed"] == 2
    assert job.json()["succeeded"] == 2
    assert job.json()["failed"] == 0
    assert job.json()["progress_percent"] == 100
    assert all(item["certificate_url"] for item in job.json()["recipients"])


def test_invalid_recipient_is_reported_without_blocking_valid_recipients(client: TestClient):
    response = client.post("/jobs", json=request_body([{"name": "Ada"}, {"name": "  "}, "not-an-object"]))

    job = client.get(response.json()["status_url"]).json()
    assert job["succeeded"] == 1
    assert job["failed"] == 2
    assert job["recipients"][1]["error"].startswith("Invalid recipient:")
    assert job["recipients"][2]["status"] == "failed"


def test_generation_failure_does_not_stop_remaining_certificates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    original_generate = main.generate_certificate

    def fail_for_ada(name: str, event_name: str, issuer: str) -> bytes:
        if name == "Ada":
            raise RuntimeError("render error")
        return original_generate(name, event_name, issuer)

    monkeypatch.setattr(main, "generate_certificate", fail_for_ada)
    response = client.post("/jobs", json=request_body([{"name": "Ada"}, {"name": "Grace"}]))

    job = client.get(response.json()["status_url"]).json()
    assert job["failed"] == 1
    assert job["succeeded"] == 1
    assert "render error" in job["recipients"][0]["error"]


def test_certificate_can_be_retrieved_as_pdf(client: TestClient):
    response = client.post("/jobs", json=request_body([{"name": "Ada Lovelace"}]))
    job = client.get(response.json()["status_url"]).json()

    certificate = client.get(job["recipients"][0]["certificate_url"])
    assert certificate.status_code == 200
    assert certificate.headers["content-type"] == "application/pdf"
    assert certificate.content.startswith(b"%PDF-")


@pytest.mark.parametrize(
    "payload",
    [
        {"event_name": "", "issuer": "Issuer", "recipients": [{"name": "Ada"}]},
        {"event_name": "Course", "issuer": "Issuer", "recipients": []},
        {"event_name": "Course", "issuer": "Issuer", "recipients": [{"name": "Ada"}], "extra": 1},
    ],
)
def test_request_validation(payload: dict, client: TestClient):
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422


def test_unknown_job_and_certificate_return_not_found(client: TestClient):
    assert client.get("/jobs/not-a-job").status_code == 404
    assert client.get("/jobs/not-a-job/certificates/not-a-recipient").status_code == 404