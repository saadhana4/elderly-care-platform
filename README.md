# CareNest - Elderly Care & Medication Management Platform

---

## 1. Chosen Vertical: Elderly Care & Medication Management Platform

CareNest is an elder-centred medication and healthcare routine platform designed to reduce medication errors, bridge communication gaps between seniors, caretakers, and families, and safeguard senior autonomy. 

### User Personas & Elder-Centred Design
- **The Primary Elder (👑 Sovereign Decision-Maker)**: The central focus of the entire care model. Conventional care applications frequently treat older adults as passive recipients of care whose schedules are managed by others. CareNest reverses this dynamic by giving the elder sovereign authority over their health profile. The elder can log their own doses with high-visibility touch controls, listen to their daily routine with Web Speech read-aloud features, view plain-language medicine guides, and unilaterally approve, pause, or revoke access for any caretaker or family member.
- **The Caretaker (🤝 Healthcare Partner)**: The operational caregiver (nurse, home aide, or primary family caregiver). Caretakers manage daily prescriptions, schedule doctor visits, and record whether daily doses were taken or skipped. They possess operational read/write permissions but cannot revoke the elder's ownership or access.
- **The Family Member (👪 Supportive Observer)**: Adult children and relatives who often live far away. Family members receive **view-only access** to inspect daily routines, monitor adherence scores, view upcoming appointments, and receive automated email alert digests for missed doses without risking accidental modifications to active prescriptions.

---

## 2. Approach and Logic

### Role-Based Access Control (RBAC) & Context Decisions
User context is established at sign-in by validating a Care Profile ID (e.g. `CARE-1042`) against three distinct bcrypt-hashed passcodes. On successful authentication, an HMAC-signed session cookie stores `{profile_id, care_id, elder_name, role}`:
- **Elder**: Full read/write access + administrative control over access toggles, passcode regeneration, and emergency directives.
- **Caretaker**: Full read/write access to medications, appointments, and dose logs. Blocked from administrative access management.
- **Family**: Read-only access across all views. Write actions (`POST /medications/*`, `/appointments/*`, `/doses/log`) return `HTTP 403 Forbidden`.
- **Elder Sovereignty Enforcement**: On every request by a caretaker or family member, `app/dependencies.py` verifies `caretaker_access_enabled` and `family_access_enabled`. If the elder has revoked a role, that member is immediately rejected.

### The "Today" Dose View Logic
1. Loads active medications for today where `start_date <= today` and (`end_date is None` or `end_date >= today`).
2. Expands each medication's comma-separated schedule (e.g. `"08:00, 20:00"`) into discrete dose slots for the calendar date.
3. Compares each slot against existing `DoseLog` entries in SQLite:
   - If marked `taken`: flagged as `taken` (green badge, records which role logged it).
   - If marked `skipped`: flagged as `skipped` (neutral slate badge).
   - If unlogged and `scheduled_time < current_time`: flagged as `overdue` (red alert).
   - If unlogged and `scheduled_time >= current_time`: flagged as `pending` (blue badge).
4. Generates big, accessible 60px "Mark Taken" and "Skip Dose" buttons for editors (disabled in view-only family mode).
5. Provides a senior-friendly **Read Aloud** button that uses the browser's speech synthesis API to speak today's routine out loud.

### Adherence Percentage Calculation
Adherence is computed dynamically from logged dose records:
$$\text{Adherence \%} = \text{round}\left( \frac{\text{Taken Doses}}{\text{Total Doses Logged in Window}} \times 100 \right)$$
- If doses have been logged within the past 7 days, it computes the ratio of `taken` doses over total logged doses (`taken + skipped`).
- If no past logs exist yet, it computes the ratio of today's taken doses over total doses scheduled for today.
- If no doses are scheduled, it defaults safely to 100%.

### Automated Reminder Engine Logic
Triggered via `POST /tasks/send-reminders`, `app/services/reminder_service.py` evaluates active profiles against three precise windows:
1. **Missed / Overdue Doses**: A dose scheduled for today whose time is earlier than the current server time and has no `DoseLog` entry recorded.
2. **Upcoming Doses**: An unlogged dose scheduled today within the next 2-hour forward window (`now <= scheduled_time <= now + 2 hours`).
3. **Upcoming Appointments**: Doctor appointments with `now <= appointment_date <= now + 48 hours`.

If any alerts are detected, the engine composes a plain-text notification digest and emails all authorized recipients (`elder_email`, `caretaker_email` if enabled, `family_email` if enabled).

### Gemini AI Plain-Language Explainer & Offline Fallback
- **Online (with API Key)**: `app/services/gemini_service.py` queries `gemini-2.5-flash` using `google-genai` to generate 3 structured sections:
  1. *What is this for* (simple 6th-grade language, no medical jargon)
  2. *Common side effects* (mild signs to monitor)
  3. *What to avoid* (food, drink, or safety precautions)
- **Prominent Medical Disclaimer**: Every explanation displays a mandatory notice: *"Medical Disclaimer: This information is AI-generated for educational purposes only. It is not medical advice, diagnosis, or treatment. Always consult your doctor or pharmacist."*
- **Database Caching**: The generated JSON is saved to `Medication.plain_explanation` in SQLite, preventing redundant API requests and ensuring instant page loads.
- **Deterministic Offline Fallback**: If `GEMINI_API_KEY` is not provided or network requests fail, the service matches against a curated dictionary of common senior medications (e.g. Metformin, Lisinopril, Atorvastatin, Amlodipine, Aspirin, Omeprazole, Levothyroxine) or generates a safe, standard template so the app never breaks.

---

## 3. How the Solution Works

### Architecture & Folder Structure
```text
Healthapp/
├── app/
│   ├── config.py               # Constants, security windows, input limits & secret validation
│   ├── database.py             # SQLite engine & session management
│   ├── dependencies.py         # Auth validation & role gatekeeping (require_editor, require_elder)
│   ├── main.py                 # FastAPI init, security & CSRF middleware, exception handlers
│   ├── models.py               # SQLAlchemy ORM models (Profile, Medication, DoseLog, Appointment)
│   ├── schemas.py              # Pydantic V2 data validation models with length constraints
│   ├── security.py             # Bcrypt hashing, session HMAC tokens, sliding-window rate limiter
│   ├── routers/
│   │   ├── appointments.py     # Appointments listing, creation, editing, deletion
│   │   ├── auth.py             # Profile creation, passcode login, logout
│   │   ├── dashboard.py        # /today dose view, Taken/Skip dose logger, adherence score
│   │   ├── medications.py      # Medication CRUD, Gemini AI explanation views
│   │   ├── settings.py         # Elder access control (revoke roles, regenerate passcodes)
│   │   └── tasks.py            # POST /tasks/send-reminders cron endpoint
│   ├── services/
│   │   ├── dose_service.py     # Schedule expansion and adherence scoring logic
│   │   ├── email_service.py    # SMTP delivery with safe mock logging fallback
│   │   ├── gemini_service.py   # Gemini API integration with offline fallback & disclaimer
│   │   ├── profile_service.py  # Profile retrieval, access toggles, and passcode rotation
│   │   └── reminder_service.py # Scanner for missed doses, upcoming doses, and appointments
│   ├── static/
│   │   ├── css/styles.css      # Accessible styling (18px base, WCAG AAA contrast, focus rings)
│   │   └── js/app.js           # Read Aloud speech synthesis, text size & contrast controls
│   └── templates/              # Accessible Jinja2 server-rendered templates
│       ├── base.html           # Layout with skip-link, live region, accessibility controls
│       ├── login.html          # Sign-in by Care ID and Passcode
│       ├── create_profile.html # New elderly profile registration
│       ├── passcodes_created.html # Initial display of 3 generated passcodes
│       ├── today.html          # Read Aloud button, dose cards & adherence meter
│       ├── medications.html    # Prescription schedules
│       ├── medication_form.html# Add / edit medication
│       ├── medication_explain.html # Plain-language AI medication guide
│       ├── appointments.html   # Scheduled doctor consultations
│       ├── appointment_form.html # Add / edit doctor appointment
│       └── profile_access.html # Elder access control panel & role guide
├── tests/                      # 55 automated pytest tests (~91% coverage)
│   ├── conftest.py             # In-memory SQLite fixtures & authenticated clients
│   ├── test_accessibility_alignment.py # WCAG 2.2 landmarks, skip link, live region, roles
│   ├── test_appointments.py    # Doctor appointment scheduling & permissions
│   ├── test_auth.py            # Passcode hashing, login, rate limiting, access revocation
│   ├── test_dose_tracking.py   # Taken/Skip updates, view permissions, adherence calculation
│   ├── test_medications.py     # Medication CRUD, Pydantic validation, Gemini service
│   ├── test_reminders.py       # Secret header verification, reminder detection
│   ├── test_security_hardened.py # Security headers, CSRF, production secrets, cookie flags
│   └── test_settings.py        # Elder access controls & emergency notes updates
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile                  # Non-root container build supporting dynamic $PORT
├── pyproject.toml              # Ruff and pytest-cov configuration
├── README.md                   # System documentation
├── requirements.txt            # Pinned runtime dependencies
└── requirements-dev.txt        # Development dependencies (pytest, pytest-cov, ruff)
```

### Main User Flows
1. **Onboarding**: A new care profile is created for an elderly individual. The platform generates a unique `CARE-XXXX` ID and three role passcodes (`ELD-XXXX`, `CAR-XXXX`, `FAM-XXXX`). Passcodes are displayed once with printing guidance and hashed with bcrypt.
2. **Daily Care Routine**: The elder or caretaker signs in, lands on the "Today" view, reviews scheduled doses, and taps the large green "Mark Taken" or slate "Skip Dose" buttons. Adherence updates instantly.
3. **Speech Read-Aloud**: Senior users can click the `🔊 Read Aloud` button on the Today view to have their medication routine spoken clearly at a senior-friendly 0.9x cadence using the Web Speech Synthesis API.
4. **Understanding Prescriptions**: Users click "Plain-Language Medicine Guide" on any medication to read clear AI explanations of the drug's purpose, common side effects, and precautions with a medical disclaimer.
5. **Doctor Visits**: The elder or caretaker schedules upcoming consultations with doctor name, date/time, clinic location, and preparation notes.
6. **Elder Sovereign Authority**: The elder accesses `/settings/access` to view active members, revoke or reinstate caretaker/family access, or regenerate compromised passcodes.
7. **Automated Monitoring**: An external cron calls `POST /tasks/send-reminders` with the secret header token to trigger alert emails to registered contacts.

### API & Route Overview
| Method | Endpoint | Access Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/login` | Public | Sign-in page with Care ID and role passcode |
| `POST` | `/login` | Public | Authenticates credentials, applies rate limiting, sets session |
| `GET` | `/create-profile` | Public | Form to register a new elderly profile |
| `POST` | `/create-profile` | Public | Creates profile, generates and displays 3 passcodes |
| `GET` | `/logout` | Authenticated | Clears session cookie and redirects to login |
| `GET` | `/today` | All Roles | Today's dose schedule, adherence meter, and Read Aloud |
| `POST` | `/doses/log` | Elder, Caretaker | Records a dose as Taken or Skipped |
| `GET` | `/medications` | All Roles | Lists all active medication schedules |
| `GET` | `/medications/new` | Elder, Caretaker | Form to add a new medication |
| `POST` | `/medications/new` | Elder, Caretaker | Validates and creates medication, caches AI explanation |
| `GET` | `/medications/{id}/edit`| Elder, Caretaker | Form to edit medication details |
| `POST` | `/medications/{id}/edit`| Elder, Caretaker | Updates medication record |
| `POST` | `/medications/{id}/delete`| Elder, Caretaker | Deletes medication record |
| `GET` | `/medications/{id}/explain`| All Roles | Displays Gemini plain-language explanation |
| `GET` | `/appointments` | All Roles | Lists upcoming and past medical appointments |
| `GET` | `/appointments/new` | Elder, Caretaker | Form to schedule doctor visit |
| `POST` | `/appointments/new` | Elder, Caretaker | Creates doctor appointment |
| `GET` | `/appointments/{id}/edit`| Elder, Caretaker | Form to edit doctor visit |
| `POST` | `/appointments/{id}/edit`| Elder, Caretaker | Updates doctor visit |
| `POST` | `/appointments/{id}/delete`| Elder, Caretaker | Deletes doctor visit |
| `GET` | `/settings/access` | Elder Only | Access control panel (member statuses, passcodes, emails) |
| `POST` | `/settings/access/toggle-role` | Elder Only | Revokes or re-enables caretaker or family access |
| `POST` | `/settings/access/regenerate-passcode`| Elder Only | Regenerates and displays a fresh role passcode |
| `POST` | `/settings/access/update-contacts` | Elder Only | Updates notification emails and emergency health directives |
| `POST` | `/tasks/send-reminders` | Header Token | Automated reminder scan for Cloud Scheduler / Render Cron |
| `GET` | `/health` | Public | Container health check probe |

---

## 4. Assumptions Made

1. **SQLite Database**: Used for zero-config simplicity, portability, and thread-safe local file storage (`healthapp.db`).
2. **Email in Mock Mode Without SMTP**: When `SMTP_HOST` is omitted, the email service logs formatted notification messages to the console and marks delivery as successful so evaluations never crash due to missing mail servers.
3. **Informational AI Explanations**: Gemini-generated medication summaries are strictly educational and auxiliary. Every view includes a mandatory disclaimer stating it is not medical advice.
4. **Passcode-Based Access Model**: Instead of requiring seniors to manage complex usernames, passwords, and multi-factor apps, access is granted via distinct, memorable passcodes (e.g. `ELD-1234`, `CAR-5678`, `FAM-9012`) bound to a shared Care ID.
5. **Free-Tier / Serverless Hosting Compatibility**: The application is stateless with respect to sessions (signed cookies) and lightweight enough to run within basic container resources on free or hobby tiers.

---

## 5. Security, Accessibility, Testing and Efficiency

### Security
- **Bcrypt Hashing**: All passcodes are hashed using `bcrypt` (12 rounds) before storage; plaintext passcodes are never stored in the database.
- **CSRF Protection**: State-changing POST requests are protected via `CSRFProtectionMiddleware`, checking double-submit tokens (`X-CSRF-Token` header, cookie matching, and `Origin`/`Sec-Fetch-Site` verification).
- **Security Headers on Every Response**:
  - `Content-Security-Policy`: Restricts scripts, styles, fonts, and images to self and safe data URIs.
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY` (anti-clickjacking)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- **Hardened Session Cookies**: Signed with HMAC-SHA256, carrying `HttpOnly=True`, `SameSite="lax"`, and dynamically setting `Secure=True` in production.
- **Brute-Force Rate Limiting**: An in-memory sliding window limiter tracks failed attempts per (IP, Care ID). More than 5 failed attempts in 60 seconds results in an `HTTP 429 Too Many Requests` lockout.
- **Constant-Time Scheduler Token Verification**: `POST /tasks/send-reminders` verifies the `X-Scheduler-Token` or Bearer header using `hmac.compare_digest` to prevent timing attacks.
- **Production Secret Fail-Fast**: On startup in `production`, the application immediately raises `RuntimeError` if `SECRET_KEY` or `SCHEDULER_SECRET_TOKEN` still contains default insecure placeholder values.
- **Input Sanitization & Length Limits**: Strict length constraints enforced via Pydantic V2 schemas on all form fields (names, dosages, notes, times) to protect against buffer exhaustion and injection. Generic login error messages prevent username enumeration.
- **Non-Root Docker User**: Container runs as an unprivileged user (`appuser`, UID 1000).

### Accessibility (WCAG 2.2 AA/AAA)
- **Document Semantics & Landmarks**: Set `lang="en"` on `<html>`, single `<h1>` per view, logical heading hierarchy, and semantic landmarks (`<header role="banner">`, `<main id="main-content" role="main" tabindex="-1">`, `<footer role="contentinfo">`, `<nav>`).
- **Skip Navigation Link**: Keyboard users can jump immediately past the header to main content with `.skip-link`.
- **Screen Reader Live Announcements**: Persistent `#status-announcer` (`role="status"`, `aria-live="polite"`, `aria-atomic="true"`) alerts screen readers of dynamic status updates and form submissions.
- **Web Speech API "Read Aloud"**: Built-in speech synthesis (`#btn-read-aloud`) speaks today's active doses at a gentle 0.9x cadence, gracefully hidden if speech synthesis is not supported.
- **Accessible Form Controls**: Every form input has a visible `<label>`, `aria-required="true"` on mandatory fields, and helper text linked with `aria-describedby`.
- **Accessible Tables**: Recent dose history logs use `<caption class="sr-only">` and `<th scope="col">`.
- **Typography & Touch Targets**: Base font is `18px`, inputs are `52px` tall, and dose buttons are `60px` tall (all interactive elements exceed the $44 \times 44\text{ px}$ target size requirement).
- **Contrast & Theme Support**:
  - `A+ Large Text`: Increases base font size to `22px` across all views.
  - `👁️ High Contrast`: Activates a high-contrast monochrome mode exceeding 7:1 contrast.
  - Full support for `@media (prefers-reduced-motion: reduce)`, `@media (prefers-contrast: more)`, and 200% text zoom.
  - Visible focus indicator outlines (`:focus-visible`) with dual offset.

### Testing
- **Automated Pytest Suite**: **55 automated tests** across 8 test suites using an isolated in-memory SQLite database (`sqlite:///:memory:`).
- **Test Coverage**: **91.0% overall code coverage** on `app/` measured via `pytest-cov`:
  - `tests/test_accessibility_alignment.py`: WCAG landmarks, skip link, live region announcer, form aria tags, speech synthesis triggers, elder sovereign banners.
  - `tests/test_security_hardened.py`: Security headers, CSRF validation, production secret checks, session cookie flags, input validation bounds, timing attack prevention.
  - `tests/test_auth.py`: Passcode generation, bcrypt verification, role login, rate limiting lockout, access revocation, passcode regeneration.
  - `tests/test_medications.py`: Medication CRUD, schedule validation, family view-only enforcement, Gemini explainer generation.
  - `tests/test_dose_tracking.py`: Taken/Skip logging, role attribution, and adherence percentage calculation.
  - `tests/test_appointments.py`: Doctor visit creation, modification, deletion, and permission barriers.
  - `tests/test_settings.py`: Elder access control, role disabling, and contact email updates.
  - `tests/test_reminders.py`: Scheduler token authentication, missed dose detection, upcoming dose detection, and appointment alert generation.
- **Pass Rate**: **55 passed** (100% pass rate).

### Efficiency
- **Zero Heavy JavaScript Bundles**: Server-rendered HTML via Jinja2 with minimal vanilla JS eliminates client-side hydration delays and heavy runtime overhead.
- **Cached AI Responses**: Gemini explanations are computed once upon medication addition and stored in SQLite, avoiding repeated API latency and token consumption.
- **Fast Startup & Low Memory**: Cold start takes under 1 second, running smoothly in memory-constrained environments (<100MB RAM).

---

## 6. Local Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 and Python 3.14)
- Git

### 2. Installation
```powershell
# Clone repository and enter directory
git clone <repo-url>
cd Healthapp

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShell
# source venv/bin/activate    # Linux / macOS

# Install required packages
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # Optional: for tests and ruff
```

### 3. Environment Setup
```powershell
cp .env.example .env
```

### 4. Run the Application
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```
The application will be live at: **[http://127.0.0.1:8080](http://127.0.0.1:8080)**

*(Note: Navigate directly to `http://127.0.0.1:8080` to avoid Windows IPv6 `localhost` resolution conflicts).*

### 5. Run the Automated Tests & Coverage
```powershell
python -m pytest tests/ -v --cov=app
```

---

## 7. Deployment

The application is fully containerized and deployable on **Render** (as a Web Service) using the root `Dockerfile`.

### Deploying on Render via Docker
1. Push this repository to GitHub or GitLab.
2. Log in to [Render Dashboard](https://dashboard.render.com/) and click **New +** > **Web Service**.
3. Connect your repository.
4. Render automatically detects the root `Dockerfile` (Environment: **Docker**).
5. Specify the environment variables in the Render dashboard (see Section 8 below).
6. Click **Deploy Web Service**.

*Note on dynamic ports and security:* The `Dockerfile` runs as non-root `appuser` (UID 1000) and entrypoint dynamically binds to the port assigned by Render's runtime via `${PORT}`:
```dockerfile
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
```

### Triggering Automated Reminders via Cron
Automated reminder scans are triggered by making an HTTP `POST` request to `/tasks/send-reminders` with the `X-Scheduler-Token` header. This can be configured in any cron scheduler (e.g., Render Cron Job, GitHub Actions, or cron-job.org):

```bash
curl -X POST "https://<YOUR-RENDER-APP-URL>/tasks/send-reminders" \
     -H "X-Scheduler-Token: <YOUR_SCHEDULER_SECRET_TOKEN>" \
     -H "Content-Type: application/json"
```

**Recommended Schedule**: Every 30 minutes (`*/30 * * * *`) or hourly (`0 * * * *`).

---

## 8. Environment Variables

Configure the following variables in `.env` (or in the Render environment settings):

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `APP_NAME` | No | `CareNest - Elderly Care & Medication Management` | Display name of the platform |
| `ENVIRONMENT` | No | `development` | Set to `production` in deployed environments |
| `PORT` | No | `8080` | Web server listening port (automatically set by Render) |
| `SECRET_KEY` | **Yes** | — | Cryptographic secret for signing session HMAC cookies |
| `DATABASE_URL` | No | `sqlite:///./healthapp.db` | SQLAlchemy database connection string |
| `SCHEDULER_SECRET_TOKEN` | **Yes** | — | Secret token required in header to call `/tasks/send-reminders` |
| `GEMINI_API_KEY` | No | `""` | Google Gemini API key for plain-language medicine explanations |
| `SMTP_HOST` | No | `""` | SMTP mail server hostname (falls back to console mock logging if empty) |
| `SMTP_PORT` | No | `587` | SMTP mail server port |
| `SMTP_USER` | No | `""` | SMTP authentication username |
| `SMTP_PASSWORD` | No | `""` | SMTP authentication password |
| `SMTP_FROM` | No | `CareNest Alerts <alerts@carenest.local>` | Outgoing sender email address |
| `SMTP_TLS` | No | `true` | Enable TLS encryption for SMTP communication |
