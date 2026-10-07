from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    course_name = Column(String, nullable=False)
    issue_date = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed
    total = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    certificates = relationship("Certificate", back_populates="job")


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    name = Column(String)
    email = Column(String)
    status = Column(String, default="pending")  # pending, success, failed
    file_path = Column(String, nullable=True)
    error = Column(String, nullable=True)

    job = relationship("Job", back_populates="certificates")
