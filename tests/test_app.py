import os
import tempfile

# these have to be set before importing the app, otherwise it uses the real db
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "test.db")
os.environ["CERT_DIR"] = os.path.join(tmp, "certs")

import io
import zipfile
import pytest
from fastapi.testclient import TestClient

import main
import certificate
from database import engine, Base

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_db():
    # fresh tables for every test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def make_payload(recipients):
    return {"course_name": "Python Basics", "issue_date": "2026-10-07", "recipients": recipients}


good = [
    {"name": "Rahul Sharma", "email": "rahul@example.com"},
    {"name": "Priya Das", "email": "priya@example.com"},
]


# creating a job
def test_create_job():
    res = client.post("/jobs", json=make_payload(good))
    assert res.status_code == 202
    data = res.json()
    assert data["total"] == 2
    assert "job_id" in data


def test_job_not_found():
    res = client.get("/jobs/999")
    assert res.status_code == 404


# validation
def test_empty_recipients():
    res = client.post("/jobs", json=make_payload([]))
    assert res.status_code == 422


def test_missing_course_name():
    res = client.post("/jobs", json={"issue_date": "2026-10-07", "recipients": good})
    assert res.status_code == 422


def test_blank_course_name():
    payload = make_payload(good)
    payload["course_name"] = "   "
    res = client.post("/jobs", json=payload)
    assert res.status_code == 422


def test_too_many_recipients():
    many = [{"name": "A" + str(i), "email": "a%d@example.com" % i} for i in range(main.MAX_RECIPIENTS + 1)]
    res = client.post("/jobs", json=make_payload(many))
    assert res.status_code == 422


def test_invalid_recipients_are_marked_failed():
    recipients = [
        {"name": "Good Person", "email": "good@example.com"},
        {"name": "", "email": "noname@example.com"},
        {"name": "Bad Email", "email": "not-an-email"},
        {"name": "No Email"},
        "just a string",
    ]
    job_id = client.post("/jobs", json=make_payload(recipients)).json()["job_id"]
    data = client.get("/jobs/" + str(job_id)).json()

    assert data["total"] == 5
    assert data["success_count"] == 1
    assert data["failed_count"] == 4
    failed = [c for c in data["certificates"] if c["status"] == "failed"]
    assert all(c["error"] for c in failed)


# certificate generation + status
def test_certificates_generated():
    job_id = client.post("/jobs", json=make_payload(good)).json()["job_id"]
    data = client.get("/jobs/" + str(job_id)).json()

    assert data["status"] == "completed"
    assert data["success_count"] == 2
    assert data["failed_count"] == 0
    for c in data["certificates"]:
        assert c["status"] == "success"
        assert c["download_url"] is not None


def test_generate_pdf_creates_file():
    path = certificate.generate_pdf("Test User", "Some Course", "2026-01-01", 1, 1)
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read(4) == b"%PDF"


# one certificate failing should not stop others
def test_single_failure_does_not_stop_job(monkeypatch):
    real_generate = certificate.generate_pdf

    def fake_generate(name, course_name, issue_date, job_id, cert_id):
        if name == "Priya Das":
            raise Exception("something broke")
        return real_generate(name, course_name, issue_date, job_id, cert_id)

    monkeypatch.setattr(certificate, "generate_pdf", fake_generate)

    job_id = client.post("/jobs", json=make_payload(good)).json()["job_id"]
    data = client.get("/jobs/" + str(job_id)).json()

    assert data["status"] == "completed"
    assert data["success_count"] == 1
    assert data["failed_count"] == 1
    failed = [c for c in data["certificates"] if c["status"] == "failed"][0]
    assert failed["name"] == "Priya Das"
    assert "something broke" in failed["error"]


# retrieving certificates
def test_download_single_certificate():
    job_id = client.post("/jobs", json=make_payload(good)).json()["job_id"]
    data = client.get("/jobs/" + str(job_id)).json()
    url = data["certificates"][0]["download_url"]

    res = client.get(url)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")


def test_download_failed_certificate_returns_404():
    recipients = [{"name": "Bad", "email": "bad"}]
    job_id = client.post("/jobs", json=make_payload(recipients)).json()["job_id"]
    cert_id = client.get("/jobs/" + str(job_id)).json()["certificates"][0]["id"]

    res = client.get("/jobs/%d/certificates/%d" % (job_id, cert_id))
    assert res.status_code == 404


def test_download_all_as_zip():
    job_id = client.post("/jobs", json=make_payload(good)).json()["job_id"]
    res = client.get("/jobs/" + str(job_id) + "/download")
    assert res.status_code == 200

    z = zipfile.ZipFile(io.BytesIO(res.content))
    assert len(z.namelist()) == 2
