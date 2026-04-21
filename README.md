# AI-Powered WhatsApp Appointment & Lead Management System

This project is an upload-ready MVP for clinics, salons, coaching classes, and other service businesses. It includes:

- A Flask WhatsApp webhook for Twilio
- OpenAI-powered replies with state-based conversation flow
- Lead capture and appointment booking
- A Streamlit dashboard for staff
- Local SQLite for development
- `DATABASE_URL` support for production deployments

## Project structure

```text
whatsapp_appointment_system/
|-- app.py
|-- ai.py
|-- db.py
|-- dashboard.py
|-- dashboard_start.py
|-- render.yaml
|-- requirements.txt
|-- .env.example
|-- .python-version
|-- .streamlit/config.toml
|-- .gitignore
`-- README.md
```

## Production-ready upload changes

This repo is now prepared for cloud upload:

- `DATABASE_URL` support was added so the API and dashboard can share one production database
- Local SQLite is still supported through `DATABASE_PATH`
- `render.yaml` was added for two-service deployment on Render
- `dashboard_start.py` was added so Streamlit can bind to the cloud-assigned `PORT`
- `.python-version` pins the Python runtime
- `.gitignore` excludes `.env`, local databases, logs, caches, and virtual environments

## Environment variables

Copy `.env.example` to `.env` for local work:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Important variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `TWILIO_VALIDATE_SIGNATURE`
- `BUSINESS_NAME`
- `BUSINESS_TYPE`
- `BUSINESS_LOCATION`
- `BUSINESS_HOURS`
- `BUSINESS_CONTACT_PERSON`
- `BUSINESS_TIMEZONE`
- `DATABASE_URL`
- `DATABASE_PATH`

Database behavior:

- If `DATABASE_URL` is set, the app uses that database
- If `DATABASE_URL` is empty, the app falls back to local SQLite using `DATABASE_PATH`

Recommended values:

- Local development: `TWILIO_VALIDATE_SIGNATURE=false` and no `DATABASE_URL`
- Production: `TWILIO_VALIDATE_SIGNATURE=true` and set a real Postgres `DATABASE_URL`

## Local setup

Install Python 3.11 or newer, then:

### Windows PowerShell

```powershell
cd C:\Users\admin\OneDrive\Desktop\whatsapp_appointment_system
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS / Linux

```bash
cd whatsapp_appointment_system
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run locally

Start the Flask backend:

```bash
python app.py
```

Start the Streamlit dashboard in another terminal:

```bash
streamlit run dashboard.py
```

Local URLs:

- API health check: `http://127.0.0.1:5000/health`
- Dashboard: `http://127.0.0.1:8501`
- WhatsApp webhook: `http://127.0.0.1:5000/whatsapp`

## Test locally without Twilio

When `TWILIO_VALIDATE_SIGNATURE=false`, simulate the WhatsApp webhook:

```powershell
curl.exe -X POST http://127.0.0.1:5000/whatsapp `
  -d "From=whatsapp:+919999999999" `
  -d "ProfileName=Demo User" `
  -d "Body=Hi"
```

Continue the conversation:

```powershell
curl.exe -X POST http://127.0.0.1:5000/whatsapp -d "From=whatsapp:+919999999999" -d "Body=Rahul Verma"
curl.exe -X POST http://127.0.0.1:5000/whatsapp -d "From=whatsapp:+919999999999" -d "Body=Skin consultation"
curl.exe -X POST http://127.0.0.1:5000/whatsapp -d "From=whatsapp:+919999999999" -d "Body=24 Apr 2026 5:30 PM"
```

## Upload to GitHub

Before uploading:

1. Keep `.env` private.
2. Do not upload `.venv`, `leads.db`, or log files.
3. Make sure your final business settings are in `.env.example` only as placeholders, not real secrets.

If you use Git:

```bash
git init
git add .
git commit -m "Prepare WhatsApp appointment system for deployment"
```

Then create a GitHub repository and push the project.

## Deploy on Render

This repo includes `render.yaml` for a recommended two-service setup:

- `whatsapp-appointment-api` for Flask
- `whatsapp-appointment-dashboard` for Streamlit

### Deploy steps

1. Push this folder to GitHub.
2. Log in to Render.
3. Create a new Blueprint deployment from your GitHub repo.
4. Render will detect `render.yaml` and create both services.
5. When prompted, set the API service environment variables:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `BUSINESS_NAME`
- `BUSINESS_TYPE`
- `BUSINESS_LOCATION`
- `BUSINESS_HOURS`
- `BUSINESS_CONTACT_PERSON`

The dashboard service automatically reuses the API service `DATABASE_URL` through the Blueprint file.

### Production database

For production, use a shared Postgres database URL from one of these providers:

- Render Postgres
- Neon
- Supabase
- Railway Postgres

Do not use local SQLite for a split cloud deployment. The Flask API and Streamlit dashboard need the same shared database.

## Connect Twilio after deployment

After the API service is live, copy its public URL and set this Twilio webhook:

```text
https://your-api-service-url/whatsapp
```

Use `HTTP POST`.

## Notes

- The dashboard currently has no authentication. Add login protection before sharing it widely with clients.
- The app uses OpenAI fallback messaging if `OPENAI_API_KEY` is not set.
- For larger production usage, you can extend this with calendar sync, notifications, and admin authentication.
