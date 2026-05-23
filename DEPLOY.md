Deployment notes

This repository contains a React frontend (Frontend/) and a Python Flask backend (Backend/). Below are concise steps to deploy each part and notes about the virtual environment.

Keep a single virtual environment
- I removed the top-level .venv directory from the workspace. Use the Backend/.venv for local Python development and deployments that rely on the Backend/requirements.txt.

Local run (quick)

- Backend (development):
  - Activate (PowerShell):
    (& "Backend\\.venv\\Scripts\\Activate.ps1")
    cd Backend
    pip install -r requirements.txt  # Note: installs TensorFlow/DeepFace (large)
    python app.py
  - Backend will run on http://127.0.0.1:8000 by default.

- Frontend (development):
  - Install and run:
    cd Frontend
    npm install
    npm run dev
  - Opens at http://localhost:5173 by default.

Deploy Frontend to Vercel

- Create a new Vercel project and point it to the Frontend directory (monorepo support).
- Build command: npm run build
- Output directory: dist
- Set environment variable VITE_API_BASE or similar to your backend URL (for example: https://your-backend.onrender.com).

Deploy Backend to Render

- Option A: Render Web Service (simple)
  - In Render, create a new Web Service.
  - Connect your repo and set the Root Directory to Backend.
  - Build Command: pip install -r requirements.txt
  - Start Command: gunicorn app:app -b 0.0.0.0:$PORT -w 4
  - Add required environment variables in Render settings: MONGO_CONNECTION_STRING, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, FLASK_SECRET_KEY, ADMIN_SECRET_KEY (optional), FACE_MODEL, FACE_DETECTOR, MATCH_THRESHOLD

- Option B: Render Docker service (recommended if TensorFlow/DeepFace install fails on the managed build)
  - Provide a Dockerfile in Backend/ that installs system deps and pip packages. Build and run via Docker on Render.

Notes and caveats

- Backend/requirements.txt includes tensorflow and deepface — these are large packages and may require a Docker-based deploy or a platform that supports their native builds. If pip install -r requirements.txt fails on Render, consider using a Docker deploy with an appropriate base image.
- Keep secrets (DB URIs, API keys) in the host's environment settings — do not commit them to source.

Next steps I can do for you:
- Add a minimal `vercel.json` to pin Frontend config (optional)
- Commit any additional infra files or push a deploy branch if you want me to

Additional notes:
- I added `Backend/Dockerfile` to help with builds that require `tensorflow`/`deepface`.
- Frontend now reads the API base from `import.meta.env.VITE_API_BASE` (set this env var in Vercel to your backend URL). The code falls back to `http://localhost:8000` when the env var is not provided.
- Backend accepts allowed CORS origins via `ALLOWED_ORIGINS` env (comma-separated). Example:
  - `ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://www.your-domain.com`
