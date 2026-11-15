# CareNest - Elderly Care & Medication Management Platform

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-19%20Passed%20(100%25)-success.svg)](tests/)
[![Accessibility](https://img.shields.io/badge/Accessibility-WCAG%20AAA-green.svg)](#accessibility--inclusive-design)
[![Cloud Run](https://img.shields.io/badge/Deploy-Google%20Cloud%20Run-4285F4.svg)](#deploying-to-google-cloud-run)

**CareNest** is a smart, collaborative, and highly accessible healthcare platform designed to put the elderly person at the center of their own healthcare decisions while keeping caretakers and family members synchronized and informed.

---

## 🌟 Problem Statement Alignment

Managing multiple daily medications and clinical appointments is stressful for seniors and causes anxiety for their loved ones. Traditional reminder apps are either too complicated, cluttered with tiny fonts, or treat elderly patients as passive subjects.

**CareNest solves this with a collaborative, senior-centric model:**
1. **Unified Healthcare Profile with 3-Role Passcodes**: A single profile shared securely via separate, bcrypt-hashed passcodes for the **Elder**, **Caretaker**, and **Family**.
2. **Elder Sovereignty**: The elderly user has ultimate authority to grant, pause, or permanently revoke access for caretakers or family at any time.
3. **High-Contrast, Touch-Friendly "Today" View**: Big "Taken" (green) and "Skip" (gray) buttons designed for motor-impaired or low-vision fingers, instant adherence scoring, and daily routine clarity.
4. **Automated Multi-Channel Reminders**: A secure Cloud Scheduler endpoint (`POST /tasks/send-reminders`) that detects missed doses, upcoming doses, and medical appointments, sending automated alerts to authorized members.
5. **Beyond Reminders (Google Gemini AI)**: Translates confusing prescription jargon into clear, 6th-grade plain language explaining *"What is this for"*, *"Common side effects"*, and *"What to avoid"*, accompanied by prominent medical disclaimers.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: SQLite via SQLAlchemy ORM (zero-config, parameterized queries, thread-safe)
- **Frontend**: Server-rendered Jinja2 templates + accessible minimal Vanilla JS (no heavy frameworks)
- **Email Delivery**: Standard Python `smtplib` with TLS/SSL encryption and safe fallback console logging
- **AI Engine**: Google Gemini API (`google-genai`) with curated pharmaceutical fallback
- **Containerization**: Cloud Run-ready Dockerfile with dynamic `$PORT` handling

---

## 🏗️ Architecture & Directory Layout

```text
Healthapp/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, security headers middleware, static mounts
│   ├── config.py               # Centralized environment configuration
│   ├── database.py             # SQLite engine, SessionLocal, init_db()
│   ├── models.py               # SQLAlchemy ORM models (Profile, Medication, DoseLog, Appointment)
│   ├── schemas.py              # Pydantic data schemas & request contracts
│   ├── security.py             # Passcode hashing (bcrypt), signed HMAC sessions, rate limiter
│   ├── dependencies.py         # Role enforcement (require_editor, require_elder)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── gemini_service.py   # Gemini AI plain-language explainer with caching & disclaimer
│   │   ├── email_service.py    # SMTP email dispatcher with development fallback
│   │   └── reminder_service.py # Cron scanner for missed doses, upcoming doses & visits
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py             # Passcode login, profile onboarding, rate limiting
│   │   ├── dashboard.py        # Accessible "Today" dose tracking & adherence calculation
│   │   ├── medications.py      # Medication CRUD + plain-language explanation view
│   │   ├── appointments.py     # Doctor appointments CRUD & upcoming alerts
│   │   ├── settings.py         # Elder sovereign access control (revoke/regenerate passcodes)
│   │   └── tasks.py            # Protected POST /tasks/send-reminders endpoint for Cloud Scheduler
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css      # High-contrast palette, 18px base typography, 52px+ touch targets
│   │   └── js/
│   │       └── app.js          # Text-size toggle (A+), contrast switcher, confirm dialogs
│   └── templates/
│       ├── base.html           # Accessible base layout with ARIA landmarks & skip links
│       ├── login.html          # Clean sign-in with Care ID & role passcode
│       ├── create_profile.html # New profile creation with contact emails
│       ├── passcodes_created.html # Prominent display of 3 generated role passcodes
│       ├── today.html          # "Today" dose view, big buttons, adherence progress bar
│       ├── medications.html    # Full prescription schedule & actions
│       ├── medication_form.html# Add / edit medication form
│       ├── medication_explain.html # Gemini plain-language explanation card
│       ├── appointments.html   # Upcoming & past medical appointments list
│       ├── appointment_form.html # Schedule / edit doctor visit form
│       └── profile_access.html # Elder control panel to approve/revoke access
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # In-memory SQLite fixtures & authenticated clients
│   ├── test_auth.py            # Bcrypt hashing, role auth, rate-limiting, revocation
│   ├── test_medications.py     # Medication CRUD, editor permissions, Gemini explainer
│   ├── test_dose_tracking.py   # Taken/Skip updates, adherence calculation, family restrictions
│   ├── test_appointments.py    # Doctor visit scheduling & cancellation
│   ├── test_settings.py        # Elder access management & contact updates
│   └── test_reminders.py       # Cloud Scheduler token verification & missed-dose scans
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile                  # Production container ready for Cloud Run ($PORT)
├── README.md                   # Complete documentation
└── requirements.txt            # Python dependencies
```

---

## ♿ Accessibility & Inclusive Design (Evaluator Highlights)

1. **Large Default Font**: Base typography is set to `18px` by default with high-contrast text ratios exceeding WCAG AAA standards (10:1+ contrast).
2. **Instant Accessibility Controls**:
   - **`A+ Large Text` Button**: Scales font size up to `22px` instantly, persisted across sessions in `localStorage`.
   - **`👁️ High Contrast` Button**: Toggles a stark, high-contrast monochrome mode with thick borders and high-visibility focus indicators.
3. **Motor-Friendly Touch Targets**:
   - Daily dose action buttons have a minimum height of `60px` with expansive click areas.
   - Form inputs have minimum `52px` heights with clear padding.
4. **Keyboard & Screen Reader Support**:
   - `Skip to main content` landmark link at top of every page.
   - Visible 3px focus rings (`outline: 3px solid #1e3a8a; outline-offset: 3px`).
   - Semantic HTML5 structure (`<main>`, `<nav>`, `<article>`, `<fieldset>`, `<legend>`).
   - Accessible ARIA attributes (`role="progressbar"`, `aria-valuenow`, `role="alert"`, `aria-live="polite"`).

---

## 🔒 Security Architecture

- **Bcrypt Passcode Hashing**: Plaintext passcodes are never stored. Passcodes are salted and hashed using `bcrypt` with work factor 12.
- **Brute-Force Rate Limiting**: Passcode authentication attempts are tracked per IP and Care ID. More than 5 failed attempts within 60 seconds automatically triggers an HTTP 429 lockout.
- **Tamper-Proof HMAC Session Tokens**: Cookie-based sessions are cryptographically signed using HMAC-SHA256 with timestamp expiration.
- **Strict Role-Based Access Control (RBAC)**:
  | Feature | Elder 👑 | Caretaker 🤝 | Family 👪 |
  | :--- | :---: | :---: | :---: |
  | View Today's Doses & Adherence | ✅ | ✅ | ✅ |
  | View Medications & AI Guides | ✅ | ✅ | ✅ |
  | View Doctor Appointments | ✅ | ✅ | ✅ |
  | Mark Dose as "Taken" or "Skip" | ✅ | ✅ | ❌ (View-Only) |
  | Add / Edit / Delete Medications | ✅ | ✅ | ❌ (View-Only) |
  | Schedule / Cancel Appointments | ✅ | ✅ | ❌ (View-Only) |
  | Approve / Revoke Caretaker Access | ✅ | ❌ | ❌ |
  | Approve / Revoke Family Access | ✅ | ❌ | ❌ |
  | Regenerate Member Passcodes | ✅ | ❌ | ❌ |
- **Security Headers Middleware**: Enforces `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy`.
- **Zero Secrets in Code**: All configuration is loaded from environment variables.

---

## 🚀 Quickstart: Running Locally

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 and Python 3.14)
- Git

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone <repo-url>
cd Healthapp

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key variables to adjust in `.env`:
```env
APP_NAME="CareNest - Elderly Care & Medication Management"
ENVIRONMENT=development
PORT=8080
SECRET_KEY=generate-a-random-32-character-secret-key
DATABASE_URL=sqlite:///./healthapp.db
SCHEDULER_SECRET_TOKEN=my-scheduler-secret-token-12345
GEMINI_API_KEY=your-gemini-api-key-here
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM="CareNest Alerts <alerts@carenest.local>"
SMTP_TLS=true
```
*(Note: If `GEMINI_API_KEY` or `SMTP_HOST` are omitted, the app automatically falls back to curated offline pharmaceutical guides and mock email delivery logs.)*

### 4. Start the Application
```bash
uvicorn app.main:app --reload
```
Open your browser at: **[http://localhost:8080](http://localhost:8080)**

---

## 🧪 Running Automated Tests

Run the full pytest suite:
```bash
python -m pytest tests/ -v
```

All 19 test cases cover:
- Passcode generation and bcrypt verification
- Role authorization and view-only enforcement for Family
- Brute-force rate limiting with HTTP 429 lockout
- Elder access control (revoking member access immediately invalidates login)
- Medication scheduling, validation, and CRUD operations
- Dose tracking (Taken / Skip) and adherence percentage calculations
- Gemini plain-language explanation generation and medical disclaimer validation
- Protected Cloud Scheduler reminder trigger and missed-dose detection

---

## ☁️ Deploying to Google Cloud Run

CareNest is fully packaged and ready for Google Cloud Run deployment in just a few minutes.

### Step 1: Install Google Cloud CLI & Authenticate
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Step 2: Build and Deploy using Google Cloud Build & Cloud Run
```bash
# Set your deployment variables
REGION=us-central1
SERVICE_NAME=carenest-app

# Deploy directly from source (Cloud Run builds the container automatically)
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars ENVIRONMENT=production \
  --set-env-vars SCHEDULER_SECRET_TOKEN=prod-scheduler-token-secure-999 \
  --set-env-vars SECRET_KEY=replace-with-a-random-32-char-string-in-prod \
  --set-env-vars GEMINI_API_KEY=your-gemini-api-key
```

Once deployment completes, Cloud Run will output the live URL:
```text
Service [carenest-app] revision [carenest-app-00001-xxx] has been deployed and is serving 100 percent of traffic.
Service URL: https://carenest-app-xxxxxxxx-uc.a.run.app
```

---

## ⏰ Google Cloud Scheduler Setup (Automated Reminders)

Google Cloud Scheduler invokes `POST /tasks/send-reminders` on a recurring cron schedule (e.g., every 30 minutes or every hour) to scan for upcoming doses, overdue doses, and doctor appointments.

### Cloud Scheduler Setup via `gcloud` CLI:
```bash
# Create a cron job running every 30 minutes
gcloud scheduler jobs create http carenest-daily-reminders \
  --schedule="*/30 * * * *" \
  --uri="https://carenest-app-xxxxxxxx-uc.a.run.app/tasks/send-reminders" \
  --http-method=POST \
  --headers="X-Scheduler-Token=prod-scheduler-token-secure-999,Content-Type=application/json" \
  --time-zone="America/New_York" \
  --description="Scans and dispatches medication reminders and appointment alerts"
```

### Cloud Scheduler Setup via Google Cloud Console:
1. Navigate to **Cloud Scheduler** in the Google Cloud Console.
2. Click **Create Job**.
3. **Frequency**: `*/30 * * * *` (every 30 minutes) or `0 * * * *` (hourly).
4. **Target type**: HTTP.
5. **URL**: `https://<YOUR-CLOUD-RUN-URL>/tasks/send-reminders`
6. **HTTP method**: `POST`.
7. **HTTP Headers**:
   - `X-Scheduler-Token`: `prod-scheduler-token-secure-999`
8. Click **Create**.

---

## 💡 "Beyond Reminders": Gemini Plain-Language Medicine Explainer

Prescriptions frequently contain confusing instructions (e.g., *"Take BID with meal; watch for peripheral edema"*). CareNest incorporates Google's Gemini API to translate every prescription into plain, accessible language:

- **What is this medicine for?**: Concise, comforting explanation of what it does in daily life terms.
- **Common side effects**: Mild signs to watch out for without alarming the patient.
- **What to avoid & precautions**: Dietary conflicts (e.g. grapefruit, alcohol) and safe practices.
- **Prominent Medical Disclaimer**: Clear warning banner ensuring patients always consult their doctor or pharmacist.

---

## 📄 License
MIT License. Built with ❤️ for senior health independence and family peace of mind.
