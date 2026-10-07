import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.certificates import generate_certificate
from app.database import Base, SessionLocal, engine as default_engine
from app.models import GenerationJob, JobRecipient
from app.schemas import JobCreate, recipient_adapter


def validation_message(errors: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in errors
    )


def process_job(job_id: str, sessions: sessionmaker[Session], storage_dir: Path) -> None:
    with sessions() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        job.status = "running"
        session.commit()

        recipients = session.scalars(
            select(JobRecipient)
            .where(JobRecipient.job_id == job_id, JobRecipient.status == "pending")
            .order_by(JobRecipient.position)
        ).all()
        for recipient in recipients:
            try:
                pdf = generate_certificate(recipient.name or "", job.event_name, job.issuer)
                certificate_path = storage_dir / f"{recipient.id}.pdf"
                certificate_path.write_bytes(pdf)
                recipient.certificate_path = str(certificate_path)
                recipient.status = "succeeded"
            except Exception as error:
                recipient.status = "failed"
                recipient.error = f"Certificate generation failed: {error}"
            session.commit()

        job.status = "completed"
        session.commit()


def create_app(
    database_engine: Engine = default_engine,
    sessions: sessionmaker[Session] = SessionLocal,
    storage_dir: Path | None = None,
) -> FastAPI:
    certificate_dir = storage_dir or Path(os.getenv("CERTIFICATE_STORAGE_DIR", "./generated"))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=database_engine)
        certificate_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="Bulk Certificate Generator", lifespan=lifespan)

    def get_session():
        with sessions() as session:
            yield session

    @app.post("/jobs", status_code=202)
    def create_job(
        payload: JobCreate,
        background_tasks: BackgroundTasks,
        session: Session = Depends(get_session),
    ):
        job = GenerationJob(
            event_name=payload.event_name,
            issuer=payload.issuer,
            status="queued",
        )
        for position, input_data in enumerate(payload.recipients):
            try:
                recipient_input = recipient_adapter.validate_python(input_data)
                recipient = JobRecipient(
                    position=position,
                    name=recipient_input.name,
                    input_data=input_data,
                    status="pending",
                )
            except Exception as error:
                errors = error.errors() if hasattr(error, "errors") else [{"loc": (), "msg": str(error)}]
                recipient = JobRecipient(
                    position=position,
                    name=input_data.get("name") if isinstance(input_data, dict) else None,
                    input_data=input_data,
                    status="failed",
                    error=f"Invalid recipient: {validation_message(errors)}",
                )
            job.recipients.append(recipient)

        session.add(job)
        session.commit()
        session.refresh(job)
        background_tasks.add_task(process_job, job.id, sessions, certificate_dir)
        return {"id": job.id, "status": job.status, "status_url": f"/jobs/{job.id}"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, session: Session = Depends(get_session)):
        job = session.scalar(
            select(GenerationJob)
            .where(GenerationJob.id == job_id)
            .options(selectinload(GenerationJob.recipients))
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        recipients = sorted(job.recipients, key=lambda item: item.position)
        total = len(recipients)
        completed = sum(item.status in {"succeeded", "failed"} for item in recipients)
        succeeded = sum(item.status == "succeeded" for item in recipients)
        failed = sum(item.status == "failed" for item in recipients)
        return {
            "id": job.id,
            "status": job.status,
            "event_name": job.event_name,
            "issuer": job.issuer,
            "created_at": job.created_at.isoformat(),
            "total": total,
            "completed": completed,
            "succeeded": succeeded,
            "failed": failed,
            "progress_percent": int(completed / total * 100),
            "recipients": [
                {
                    "id": item.id,
                    "name": item.name,
                    "status": item.status,
                    "error": item.error,
                    "certificate_url": (
                        f"/jobs/{job.id}/certificates/{item.id}"
                        if item.status == "succeeded"
                        else None
                    ),
                }
                for item in recipients
            ],
        }

    @app.get("/jobs/{job_id}/certificates/{recipient_id}")
    def get_certificate(
        job_id: str, recipient_id: str, session: Session = Depends(get_session)
    ):
        recipient = session.scalar(
            select(JobRecipient).where(
                JobRecipient.id == recipient_id,
                JobRecipient.job_id == job_id,
            )
        )
        if recipient is None or recipient.status != "succeeded" or not recipient.certificate_path:
            raise HTTPException(status_code=404, detail="Certificate not found")
        path = Path(recipient.certificate_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Certificate file is unavailable")
        return FileResponse(path, media_type="application/pdf", filename=f"certificate-{recipient.id}.pdf")

    return app


app = create_app()