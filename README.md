# Bulk Certificate Generator

A FastAPI service that accepts a batch of recipients, records a generation job in SQLite, and creates one downloadable PDF certificate per valid recipient. Each recipient is validated and processed independently, so one bad row or PDF-generation failure does not block the rest.

## Setup and run

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API docs are at `/docs`. By default, SQLite data is stored in `certificates.db` and generated PDFs in `generated/`. Set `DATABASE_URL` and `CERTIFICATE_STORAGE_DIR` to override these paths.

## Submit a batch

`POST /jobs` accepts 1-1000 recipients. `event_name` and `issuer` are shared by the batch; each recipient must contain a non-blank name and no other fields. Recipient-level validation errors are stored as failed results instead of rejecting the entire batch. Invalid top-level input returns HTTP 422.

```powershell
curl.exe -X POST http://127.0.0.1:8000/jobs `
	-H "Content-Type: application/json" `
	-d '{"event_name":"Python Foundations","issuer":"Example Academy","recipients":[{"name":"Ada Lovelace"},{"name":"Grace Hopper"}]}'
```

The response is HTTP 202 and includes a job ID and `status_url`.

## Track and retrieve results

Poll `GET /jobs/{job_id}`. The response includes the job status, total/completed/succeeded/failed counts, percentage progress, and each recipient's result. Failed recipient rows include an error message; successful rows include a certificate URL.

Download a successful certificate using `GET /jobs/{job_id}/certificates/{recipient_id}`. The response is a PDF; unknown, failed, or unavailable certificates return HTTP 404.

## Tests

```powershell
python -m pytest
```

Tests use an isolated in-memory SQLite database and temporary PDF storage.

## Design decisions and limits

- FastAPI `BackgroundTasks` keeps submission responsive without requiring a separate broker or worker service. SQLite persists job and per-recipient progress; generation commits each outcome independently, and the PDF layout is a single predefined ReportLab template.
- This is intended for a simple single-instance deployment and batches up to 1000 recipients. FastAPI background tasks run in the API process and are not durable: a process crash can interrupt a job. A production multi-instance or high-volume deployment should move processing to a durable queue and use shared file/object storage.
- Generated files are stored by recipient ID, not by user-supplied names. There is no authentication, expiration, or cleanup policy in this interview-sized service; deploy behind appropriate access controls before exposing certificate data publicly.