#+ FORENSIGHT — Criminal Identification

> Web application for criminal identification with a React (Vite) frontend and a Flask backend.

## Summary

- Frontend: Vite + React (in `Frontend/`)
- Backend: Flask (in `Backend/`)
- Image storage and processing: configurable via environment variables (Cloudinary shown in code)

## Quick Start (development)

### Prerequisites:

- Python 3.8+
- Node.js 16+ and npm (or pnpm/yarn)

### Backend (Windows PowerShell)

```powershell
cd Backend
python -m venv venv
.
venv\\Scripts\\Activate.ps1
pip install -r requirements.txt    # if present
# set environment variables (example):
$env:FLASK_SECRET_KEY = "your-secret"
$env:CLOUDINARY_API_KEY = "<key>"
$env:CLOUDINARY_API_SECRET = "<secret>"
python app.py
```

### Frontend

```bash
cd Frontend
npm install
npm run dev
```

## Environment / Secrets

**SECURITY NOTICE: Never commit actual secrets or API keys to this repository!**

- This repo includes a comprehensive `.gitignore` that ignores `.env` files, `node_modules/`, and other sensitive directories.
- For local development, copy `.env.example` to `.env` and fill in your actual values.
- Use environment variables for all sensitive data (API keys, database connections, etc.).
- The backend code is already configured to read from environment variables using `os.getenv()`.

### Setting up Environment Variables

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your actual values (this file is ignored by Git).

3. For production, set environment variables in your deployment platform (Heroku, Railway, etc.).

### Required Environment Variables

- `FLASK_SECRET_KEY`: Secret key for Flask sessions
- `MONGO_CONNECTION_STRING`: MongoDB connection URL
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: For image storage
- `MATCH_THRESHOLD`, `FACE_MODEL`, `FACE_DETECTOR`: Face recognition settings

## Repository cleanup

- I removed `node_modules` from the tip commit and added a `.gitignore`.
- If you want a full history purge (remove past large or sensitive files from history), run `git-filter-repo` locally and force-push; I can help with that.

## Repository cleanup

- I removed `node_modules` from the tip commit and added a `.gitignore`.
- If you want a full history purge (remove past large or sensitive files from history), run `git-filter-repo` locally and force-push; I can help with that.

## Notes

- Face-search performance: face-matching can be slow depending on dataset size and algorithm; consider indexing, caching, or using a precomputed embedding index (e.g., Faiss) to speed lookups.

## License & Contact

- This project currently has no license set. Add a `LICENSE` file if you want to set terms.
- Questions: open an issue or ask in the repository.
