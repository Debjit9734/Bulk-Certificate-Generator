import io
import os
import re
import zipfile

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

import models
import schemas
import certificate
from database import engine, get_db, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bulk Certificate Generator")

MAX_RECIPIENTS = 1000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_recipient(recipient):
    """Returns an error message if the recipient is invalid, else None."""
    if not isinstance(recipient, dict):
        return "recipient must be an object with name and email"

    name = recipient.get("name")
    email = recipient.get("email")

    if not isinstance(name, str) or name.strip() == "":
        return "name is required"
    if len(name) > 100:
        return "name is too long (max 100 characters)"
    if not isinstance(email, str) or not EMAIL_PATTERN.match(email):
        return "email is invalid"
    return None


def process_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        job.status = "processing"
        db.commit()

        certs = db.query(models.Certificate).filter(
            models.Certificate.job_id == job_id,
            models.Certificate.status == "pending",
        ).all()

        for cert in certs:
            try:
                path = certificate.generate_pdf(
                    cert.name, job.course_name, job.issue_date, job.id, cert.id
                )
                cert.file_path = path
                cert.status = "success"
                job.success_count += 1
            except Exception as e:
                # one failure should not stop the rest
                cert.status = "failed"
                cert.error = "generation failed: " + str(e)
                job.failed_count += 1
            db.commit()

        job.status = "completed"
        db.commit()
    finally:
        db.close()


@app.post("/jobs", status_code=202)
def create_job(data: schemas.JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if data.course_name.strip() == "":
        raise HTTPException(status_code=422, detail="course_name cannot be empty")
    if data.issue_date.strip() == "":
        raise HTTPException(status_code=422, detail="issue_date cannot be empty")
    if len(data.recipients) == 0:
        raise HTTPException(status_code=422, detail="recipients cannot be empty")
    if len(data.recipients) > MAX_RECIPIENTS:
        raise HTTPException(status_code=422, detail="too many recipients, max is " + str(MAX_RECIPIENTS))

    job = models.Job(
        course_name=data.course_name.strip(),
        issue_date=data.issue_date.strip(),
        total=len(data.recipients),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    for r in data.recipients:
        error = check_recipient(r)
        if error:
            
            name = r.get("name") if isinstance(r, dict) else None
            email = r.get("email") if isinstance(r, dict) else None
            cert = models.Certificate(
                job_id=job.id,
                name=str(name) if name is not None else None,
                email=str(email) if email is not None else None,
                status="failed",
                error=error,
            )
            job.failed_count += 1
        else:
            cert = models.Certificate(job_id=job.id, name=r["name"].strip(), email=r["email"])
        db.add(cert)
    db.commit()

    background_tasks.add_task(process_job, job.id)

    return {"job_id": job.id, "status": job.status, "total": job.total}


@app.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    certs = []
    for c in job.certificates:
        item = schemas.CertificateOut.model_validate(c)
        if c.status == "success":
            item.download_url = "/jobs/" + str(job.id) + "/certificates/" + str(c.id)
        certs.append(item)

    return schemas.JobOut(
        id=job.id,
        course_name=job.course_name,
        issue_date=job.issue_date,
        status=job.status,
        total=job.total,
        success_count=job.success_count,
        failed_count=job.failed_count,
        certificates=certs,
    )


@app.get("/jobs/{job_id}/certificates/{cert_id}")
def download_certificate(job_id: int, cert_id: int, db: Session = Depends(get_db)):
    cert = db.query(models.Certificate).filter(
        models.Certificate.id == cert_id,
        models.Certificate.job_id == job_id,
    ).first()
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status != "success" or not cert.file_path or not os.path.exists(cert.file_path):
        raise HTTPException(status_code=404, detail="Certificate is not available")

    return FileResponse(cert.file_path, media_type="application/pdf", filename="certificate_" + str(cert.id) + ".pdf")


@app.get("/jobs/{job_id}/download")
def download_all(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    certs = db.query(models.Certificate).filter(
        models.Certificate.job_id == job_id,
        models.Certificate.status == "success",
    ).all()
    if len(certs) == 0:
        raise HTTPException(status_code=404, detail="No certificates generated yet")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for c in certs:
            if os.path.exists(c.file_path):
                z.write(c.file_path, "certificate_" + str(c.id) + ".pdf")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=job_" + str(job_id) + ".zip"},
    )
