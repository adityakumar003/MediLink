# 🏥 AI-Based Medical Report Analyzer

> An intelligent full-stack system for uploading medical lab reports, automatically extracting structured data, predicting disease risks, and providing AI-powered health insights — designed for both patients and their doctors.

---

## 📋 Table of Contents

- [Project Purpose & Key Features](#-project-purpose--key-features)
- [Full Tech Stack](#-full-tech-stack)
- [Folder Structure Overview](#-folder-structure-overview)
- [Environment Variables](#-environment-variables)
- [Running the Backend](#-running-the-backend-locally)
- [Running the Frontend](#-running-the-frontend-locally)
- [MongoDB Atlas Setup](#-mongodb-atlas-setup)
- [Hugging Face Space (default LLM)](#-hugging-face-space-default-llm)
- [Optional Ollama Setup](#-optional-ollama-setup)
- [Video Consultations (LiveKit Cloud)](#-video-consultations-livekit-cloud)
- [Running Tests](#-running-tests)
- [Docker Compose](#-running-with-docker-compose)
- [MVP Scope vs Future Modules](#-mvp-scope-vs-future-modules)
- [Development Roadmap](#-development-roadmap)

---

## 🎯 Project Purpose & Key Features

### Purpose
Patients generate medical lab reports regularly, but most people lack the medical expertise to understand them. This system bridges that gap by:

1. **Accepting PDF or image uploads** of medical lab reports
2. **Extracting text** from digital PDFs (PyMuPDF) and scanned pages/images (PaddleOCR)
3. **Sending the text to a hosted Qwen model** (Hugging Face Space) for a cautious explanation
4. **Classifying values in Python** against the reference range printed on that report
5. **Presenting results** in a clear, patient-friendly dashboard
6. **Allowing doctors** to view their patients' reports securely

### Key Features (MVP — Phase 1)
| Feature | Status |
|---------|--------|
| Patient registration & JWT authentication | ✅ Complete |
| Doctor registration with unique doctor_id | ✅ Complete |
| PDF and image report upload | ✅ Complete |
| Text extraction via PyMuPDF + PaddleOCR | ✅ Complete |
| Hugging Face Qwen report analysis | ✅ Default (`AI_MODE=hf_space`) |
| Offline report analysis | ✅ Complete (`AI_MODE=offline`) |
| Ollama-powered report analysis | ✅ Optional (`AI_MODE=ollama`) |
| Patient dashboard | ✅ Complete |
| Doctor dashboard with patient management | ✅ Complete |
| Doctor–patient connection and chat | ✅ Complete |
| 1:1 doctor–patient video consultations (LiveKit Cloud) | ✅ Complete |
| GPS-based nearby doctor discovery | ✅ Complete |

---

## 🛠 Full Tech Stack

### Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10+ | Core language |
| FastAPI | 0.111.0 | Async web framework |
| Uvicorn | 0.29.0 | ASGI server |
| Motor | 3.4.0 | Async MongoDB driver |
| Beanie ODM | 1.26.0 | Typed MongoDB document models |
| Pydantic | 2.7.1 | Data validation & serialization |
| pydantic-settings | 2.2.1 | Settings from environment |
| python-jose | 3.3.0 | JWT creation & verification |
| passlib[bcrypt] | 1.7.4 | Password hashing |
| python-multipart | 0.0.9 | File upload support |
| python-dotenv | 1.0.1 | .env file loading |
| httpx | 0.27.0 | HTTP client (Ollama path) |
| gradio-client | ≥2.7.0 | Hugging Face Gradio Space client |
| PyMuPDF | 1.24.3 | Primary PDF text extraction |
| LiveKit Python SDK | 2.0.0 | Room-scoped access-token generation |
| pytest | 8.2.0 | Test framework |
| pytest-asyncio | 0.23.6 | Async test support |

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 18.3.x | UI framework |
| TypeScript | 5.4.x | Type safety |
| Vite | 5.2.x | Build tool & dev server |
| React Router | 6.23.x | Client-side routing |
| Axios | 1.7.x | HTTP client |
| TailwindCSS | 3.4.x | Utility-first CSS framework |
| React Hook Form | 7.51.x | Form state management |
| Zod | 3.23.x | Schema validation |
| LiveKit Client | 2.24.x | WebRTC room, camera, microphone |
| LiveKit React Components | 2.9.x | Room lifecycle, tracks, audio rendering |
| LiveKit Component Styles | 1.2.x | Accessible base styles for media controls |

### Database
| Technology | Purpose |
|-----------|---------|
| MongoDB Atlas | Cloud-hosted NoSQL database |
| Motor | Async Python driver |
| Beanie ODM | Typed document models over Motor |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| Docker + Docker Compose | Container orchestration |
| .env files | Secret & config management |
| Local filesystem | MVP file storage (`backend/uploads/`) |

---

## 📁 Folder Structure Overview

```
medical-report-analyzer/
├── frontend/                    # React + Vite + TypeScript
│   └── src/
│       ├── components/          # Reusable UI components
│       │   ├── common/          # Navbar, Sidebar, ProtectedRoute, etc.
│       │   ├── auth/            # LoginForm, RegisterForm
│       │   ├── patient/         # ReportUpload, DiseaseRiskCard, etc.
│       │   ├── doctor/          # PatientList, RequestCard, etc.
│       │   └── video/           # Consultation list + doctor scheduling UI
│       ├── pages/               # Route-level page components (incl. video/VideoCallPage)
│       ├── layouts/             # Page wrapper layouts
│       ├── context/             # AuthContext (global auth state)
│       ├── hooks/               # useAuth, useReportUpload
│       ├── services/            # Axios API calls (api.ts, authService.ts, ...)
│       ├── types/               # TypeScript interfaces
│       └── utils/               # Shared helper functions
│
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app + lifespan + CORS + routers
│       ├── api/
│       │   ├── dependencies.py  # JWT auth guards, role checks
│       │   └── routes/          # auth, doctors, patients, reports, analysis, video
│       ├── models/              # Beanie document models (MongoDB collections)
│       ├── schemas/             # Pydantic request/response schemas
│       ├── services/            # Business logic layer
│       ├── ai/
│       │   ├── ollama/          # Optional local Ollama prompts
│       │   ├── ocr/             # Unused stub; live OCR is in text_extraction_service
│       │   ├── nlp/             # Future: BioBERT NER
│       │   ├── disease_prediction/ # Future: XGBoost/LightGBM models
│       │   └── explainability/  # Future: SHAP
│       ├── core/                # config.py, database.py, security.py
│       └── utils/               # file_utils.py, response_utils.py
│   ├── tests/                   # pytest test suite
│   ├── uploads/                 # Local PDF storage (gitignored)
│   ├── requirements.txt
│   └── .env.example
│
├── data/                        # Future: training datasets
├── models/                      # Future: ML model weights
├── notebooks/                   # Future: EDA and training notebooks
├── scripts/                     # Future: data prep scripts
├── docs/                        # Future: API docs and architecture diagrams
├── docker/
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 🔐 Environment Variables

Copy `backend/.env.example` to `backend/.env`. Never commit `.env` (it is gitignored).

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URL` | Production | Full MongoDB Atlas connection string |
| `DATABASE_NAME` | ✅ | MongoDB database name (default: `medical_report_analyzer`) |
| `USE_IN_MEMORY_DB` | ✅ | `true` for zero-setup local use; `false` for MongoDB |
| `SECRET_KEY` | ✅ | Secret key for JWT signing — use `openssl rand -hex 32` |
| `ALGORITHM` | ✅ | JWT algorithm (default: `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ✅ | Token lifetime in minutes (default: `30`) |
| `AI_MODE` | ✅ | `hf_space` (default), `gemini`, `ollama`, or `offline`. No silent fallback. |
| `ENABLE_LLM_SUMMARY` | ✅ | `true` (default) enables LLM narrative; `false` disables **all** LLM calls and uses the deterministic pipeline with a template summary. |
| `HF_SPACE_URL` | HF default | `https://huggingface.co/spaces/adityaksingh/MediBridge-qwen` |
| `HF_TOKEN` | Usually empty | Backend-only. Set only if the Space is private. Never put this in frontend env. |
| `HF_TIMEOUT_SECONDS` | HF default | Wait time for Space inference (default `120`) |
| `OLLAMA_BASE_URL` | Ollama only | Local Ollama service URL |
| `OLLAMA_MODEL` | Ollama only | Installed model name |
| `LIVEKIT_URL` | Video | `wss://your-project.livekit.cloud` from LiveKit Cloud |
| `LIVEKIT_API_KEY` | Video | LiveKit API key — backend only, never frontend |
| `LIVEKIT_API_SECRET` | Video | LiveKit API secret — backend only, never frontend |
| `LIVEKIT_TOKEN_TTL_MINUTES` | ✅ | Participant token lifetime (default `60`, min `5`) |
| `ALLOWED_ORIGINS` | ✅ | CORS allowed origins (default: `http://localhost:5173`) |
| `UPLOAD_DIR` | ✅ | Directory for uploaded files (default: `uploads`) |
| `MAX_FILE_SIZE_MB` | ✅ | Upload size limit in MB (default: `10`) |
| `ENVIRONMENT` | ✅ | `development` / `staging` / `production` |

---

## 🚀 Running the Backend Locally

### Prerequisites
- Python 3.10+
- pip
- MongoDB Atlas only when persistent storage is required
- Network access to Hugging Face when `AI_MODE=hf_space`
- Ollama only when `AI_MODE=ollama`

### Steps

```bash
# 1. Navigate to the backend directory
cd medical-report-analyzer/backend

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env     # Windows
# cp .env.example .env     # macOS/Linux
# The default file uses an in-memory database and Hugging Face Space analysis.

# 5. Create the uploads directory (if it doesn't exist)
mkdir -p uploads

# 6. Run the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## ⚛️ Running the Frontend Locally

### Prerequisites
- Node.js 18+ and npm

### Steps

```bash
# 1. Navigate to the frontend directory
cd medical-report-analyzer/frontend

# 2. Install dependencies
npm install

# 3. (Optional) Point the frontend at a separate API origin
# Create frontend/.env.local only when NOT using Vite's dev proxy:
# VITE_API_URL=http://localhost:8000

# 4. Start the Vite dev server
npm run dev
```

The frontend will be available at: **http://localhost:5173**

> **Note**: The Vite dev server is configured with a proxy. All requests to `/auth`, `/doctors`, `/patients`, `/reports`, `/analysis`, `/chat`, `/video`, and `/health` are automatically forwarded to `http://localhost:8000`. Leave `VITE_API_URL` empty for this setup.
>
> LiveKit credentials are intentionally **not** frontend environment variables. The browser receives only a short-lived, room-scoped token from `POST /video/token`.

---

## 🌐 MongoDB Atlas Setup

1. Go to [https://cloud.mongodb.com](https://cloud.mongodb.com) and create a free account.
2. Create a new **Project**.
3. Click **"Build a Database"** → Select **M0 Free Tier** → Choose your region.
4. Set up a **Database User**:
   - Username: `your_username`
   - Password: generate a secure password (save it!)
5. Under **Network Access**, click **"Add IP Address"** → select **"Allow Access from Anywhere"** (0.0.0.0/0) for development.
6. Click **Connect** → **"Connect your application"** → **Python / Motor**.
7. Copy the connection string. Replace `<password>` with your actual password and `<dbname>` with `medical_report_analyzer`.
8. Paste this URL as `MONGODB_URL` in your `backend/.env` file.

---

## 🤗 Hugging Face Space (default LLM)

Default analysis uses the public Gradio Space:

`https://huggingface.co/spaces/adityaksingh/MediBridge-qwen`

It serves `Qwen/Qwen2.5-3B-Instruct` on Hugging Face ZeroGPU. The backend calls the Gradio `/analyze` endpoint via `gradio-client`. This is **not** an OpenAI-compatible chat-completions URL.

```env
AI_MODE=hf_space
HF_SPACE_URL=https://huggingface.co/spaces/adityaksingh/MediBridge-qwen
HF_TOKEN=
HF_TIMEOUT_SECONDS=120
```

- Leave `HF_TOKEN` empty for the public Space.
- If authentication is required later, set a token in **backend** `.env` only.
- ZeroGPU may cold-start: the first request can take tens of seconds (the Space GPU budget is ~90s). Free-tier queues and rate limits can return HTTP 503; retry from the UI.
- Hugging Face failures do **not** silently fall back to Ollama. Switch `AI_MODE` explicitly if you want another provider.

### Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Analysis times out | Retry after 30–60s (cold start). Increase `HF_TIMEOUT_SECONDS`. |
| 503 authentication | Space may be private; set `HF_TOKEN` in backend `.env`. |
| 503 rate limit / quota | Wait and retry; ZeroGPU free tier is shared. |
| 422 extracted text too short | PDF may be blank/scanned without OCR. Install PaddleOCR for images. |
| 502 unparseable analysis | Retry; the model returned unstructured text. |

## 🤖 Optional Ollama Setup

Ollama is **not** required for the default hosted-inference workflow. To use a local model instead:

```env
AI_MODE=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
```

For local-only extraction without any LLM:

```env
AI_MODE=offline
```

## ✨ Optional Gemini Setup

Google Gemini can generate the report summary instead of the Hugging Face Space.
It uses the same response contract: Gemini writes the structured analysis and
Python still validates every numerical status, so the model cannot override
validated Low/Normal/High classifications.

```env
AI_MODE=gemini
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
```

- Get a key at https://aistudio.google.com/apikey — keep it in backend `.env` only, never in frontend code.
- Switch back to Hugging Face with one change: `AI_MODE=hf_space`.
- Gemini failures do **not** silently fall back to another provider.

## 🎥 Video Consultations (LiveKit Cloud)

The chat feature remains a separate persisted messaging system. Video calls use LiveKit Cloud only for the real-time media transport.

### 1. Create a free LiveKit Cloud project

1. Sign in at https://cloud.livekit.io and create a project on the free tier.
2. Open **Settings → Keys** and copy the WebSocket URL, API key, and API secret.
3. Put them in `backend/.env`:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_TOKEN_TTL_MINUTES=60
```

No LiveKit variables belong in the frontend `.env`. Without these backend values, consultation records still work but `POST /video/token` returns **503** until configuration is complete.

### 2. How authorization works

- A doctor can start or schedule a consultation only for an **accepted** patient connection (`DoctorPatientRequest.status == accepted`).
- The authenticated JWT identifies the user. The frontend never supplies a room name, participant identity, or role.
- The backend derives the room from the consultation record and issues a participant-specific LiveKit token with:
  - `roomJoin` scoped to exactly one consultation room
  - audio/video publish and subscribe permissions
  - a server-configured expiry
- Both participants share the same consultation record and room. A patient cannot join before the doctor starts it.

### 3. Lifecycle

- `scheduled → started → in_progress → completed`
- `cancelled` is available for scheduled or not-yet-joined consultations.

- Starting a consultation does **not** pre-create a LiveKit room. The room is created when the first participant joins and LiveKit closes it after it becomes empty.
- Temporary network disconnects do not mark a consultation completed. Only an explicit doctor **End** action or both participants explicitly leaving completes it.
- When the doctor ends the call, the backend completes the record and the doctor sends an in-room notification so the patient's UI does not treat the end as a network error.
- Camera, microphone, and screen-sharing resources are owned by LiveKit and released when the room screen unmounts.

### 4. API endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/video/consultations` | Doctor starts now (omit `scheduled_at`) or schedules for later |
| `GET` | `/video/consultations` | Current user's consultation history |
| `GET` | `/video/consultations/{id}` | One authorized consultation |
| `POST` | `/video/consultations/{id}/start` | Doctor starts a scheduled consultation |
| `POST` | `/video/token` | Issue a room-scoped LiveKit token for the authenticated participant |
| `POST` | `/video/consultations/{id}/leave` | Record an intentional leave |
| `POST` | `/video/consultations/{id}/end` | Doctor ends and completes the consultation |
| `POST` | `/video/consultations/{id}/cancel` | Cancel a scheduled/not-yet-joined consultation |

### 5. Free-tier boundaries

This implementation does not use LiveKit Agents, recording, transcription, egress, or SIP. It only uses room join plus audio/video publication. Browser camera/microphone access requires `https://` or `localhost`.

### 6. Two-participant verification

1. Connect a patient and doctor through the normal request/accept flow.
2. Sign in as the doctor in one browser profile and the patient in another.
3. On the doctor's **Video** page, choose the patient and click **Start now** (or **Schedule** and later **Start**).
4. Allow camera/microphone access. In the patient's **Video** page, click **Join** once the status is **Ready to join**.
5. Verify mute/camera controls, the connection indicator, the remote participant name/role, and that both participants see each other.
6. Click **End** as the doctor and confirm the patient leaves automatically. A scheduled call can be cancelled by either participant before it starts.
7. Regression-check login, report analysis, and the existing **Chats** page, which remains independent of LiveKit.

## 🧪 Running Tests

```bash
cd medical-report-analyzer/backend
python -m pytest
```

Automated tests force `AI_MODE=offline` for upload/history integration and **mock** Hugging Face (`gradio_client`), Gemini (`google.genai`), and PaddleOCR for provider/extraction tests. They do not call live models and do not require PaddlePaddle.

Video tests use deterministic fake LiveKit credentials to verify consultation lifecycle, participant authorization, role guards, and signed room-scoped token grants. They do **not** connect to a LiveKit Cloud project; real two-browser media testing requires your own LiveKit credentials and camera/microphone permissions.

### PaddleOCR environment note

PaddlePaddle 2.x is incompatible with `protobuf>=4` (`Descriptors cannot be
created directly`), while `google-genai` requires modern protobuf — so neither
package version can simply change. The backend therefore forces protobuf's
pure-Python implementation for the OCR stack in code (`app/main.py`, no action
needed). If you prefer native speed, the proper fix is migrating to
PaddlePaddle/PaddleOCR 3.x.

## 🩺 Disease Risk Assessment Engine

Risk cards are produced by a **deterministic backend engine** (`backend/app/services/risk_assessment.py`), not by the LLM and not by a validated clinical risk model:

- Each condition returns an explicit state: `assessed`, `insufficient_data`, `not_assessed`, or `requires_review`.
- A risk level appears **only** when an adequate marker set supports it; otherwise the card shows the evidence, the missing inputs, the method (if any), and clinician-review guidance.
- Examples of deliberate restraint: a lone normal creatinine never yields a CKD claim; total cholesterol alone never yields an overall cardiovascular category (no validated calculator is implemented); an abnormal marker yields `requires_review`, never a diagnosis.
- The LLM (when enabled) only writes the narrative summary from validated results, and a consistency guard replaces summaries that contradict validated abnormal findings. Numerical statuses always come from `lab_validation.py`.

To disable every LLM call (zero API cost/quota): `ENABLE_LLM_SUMMARY=false`. The parameter table, states, and template summary keep working.

> **Clinical validation status:** the engine's rules are evidence-grounded heuristics reviewed against the sample report, covered by unit tests — they are **not** a clinically validated risk model. Formal validation would require a clinician-adjudicated reference set: collect de-identified reports spanning normal/borderline/abnormal/incomplete/noisy cases, have clinicians label the appropriate assessment state per condition, and measure engine agreement before any clinical reliance.

---

## 🐳 Running with Docker Compose

### Prerequisites
- Docker Desktop installed and running

### Steps

```bash
# 1. Navigate to the project root
cd medical-report-analyzer

# 2. Ensure backend/.env exists with all required values
# (copy from .env.example and fill in real values)

# 3. Build and start all services
docker compose up --build

# 4. To run in detached (background) mode:
docker compose up --build -d

# 5. To stop services:
docker compose down
```

**Services:**
| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:5173 |

> **Note**: MongoDB is hosted on Atlas — no local MongoDB container is needed or included.

---

## 📦 MVP Scope vs Future Modules

### ✅ MVP (Phase 1 — Current)
- User registration & JWT authentication (patient + doctor roles)
- Doctor profile with unique doctor_id
- Doctor–patient connection request system
- Medical PDF/image report upload (local storage)
- PDF text extraction: PyMuPDF, with PaddleOCR for scanned pages and images
- AI analysis via Hugging Face Qwen Space (optional Ollama or offline)
- Structured data extraction (parameters, risks) mapped to the existing API contract
- Patient dashboard (upload, view analysis)
- Doctor dashboard (manage patients, view reports)
- Secure 1:1 video consultations with LiveKit Cloud (schedule, join, leave, end)

### 🔜 Phase 2 — Advanced OCR & NER
- Stronger OpenCV preprocessing (denoising, deskewing, contrast)
- BioBERT / ClinicalBERT NER for medical entity extraction
- Support for more complex multi-page layouts

### 🔮 Phase 3 — ML Disease Prediction & Explainability
- XGBoost + LightGBM disease prediction models:
  - Diabetes (HbA1c, FPG, BMI)
  - Chronic Kidney Disease (creatinine, eGFR, BUN)
  - Anemia (hemoglobin, MCV, MCH)
  - Cardiovascular risk (cholesterol, LDL, HDL)
- SHAP TreeExplainer for transparent predictions
- MLflow for model versioning and experiment tracking
- PDF report generation (reportlab / WeasyPrint)
- AWS S3 or Cloudinary for scalable file storage

---

## 🗺 Development Roadmap

```
Phase 1 (MVP)          Phase 2 (OCR/NER)      Phase 3 (ML Models)
─────────────          ─────────────────       ───────────────────
Auth system      →     PaddleOCR pipeline →    Disease prediction
Report upload          OpenCV preprocessing    SHAP explanations
PyMuPDF + OCR          BioBERT NER             MLflow tracking
Hugging Face Qwen      Layout improvements     PDF report export
Patient dashboard      Improved accuracy       S3 file storage
Doctor dashboard       Multi-page support      Production deploy
```

**Current Phase**: ✅ **Phase 1 MVP complete**

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Follow the architecture rules: Routes → Services → AI/Database
4. Add tests for new endpoints in `backend/tests/`
5. Open a Pull Request

---

## 📄 License

This project is for educational and research purposes.
