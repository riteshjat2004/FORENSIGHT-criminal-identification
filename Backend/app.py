import os
# Configure TensorFlow, OpenBLAS, and MKL thread limits BEFORE any other imports
# Prevents spawning 64+ threads on cloud hosts (Render/AWS), which causes 512MB RAM OOM crashes.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import io
import numpy as np
from datetime import datetime, timezone
import multiprocessing
import threading
import re
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for, jsonify, g
from PIL import Image
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import cloudinary
import cloudinary.uploader

# ==============================
# LOAD ENV
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

# ==============================
# CONFIG
# ==============================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")

_token_serializer = URLSafeTimedSerializer(app.secret_key, salt="auth")
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7

# MongoDB
client = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
db = client["face_recognition_db"]
collection = db["criminals"]
users_collection = db["users"]

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# SETTINGS
THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.3"))
MODEL = os.getenv("FACE_MODEL", "Facenet512")
DETECTOR = os.getenv("FACE_DETECTOR", "opencv")
ENFORCE = os.getenv("ENFORCE_DETECTION", "false").lower() in {"1", "true", "yes"}
TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "180"))

# Frontend origins (Vite) — configurable via `ALLOWED_ORIGINS`
# Provide a comma-separated list of allowed origins (example: https://app.example.com,https://www.example.com)
# Use `ALLOWED_ORIGINS='*'` to allow all origins.
_DEFAULT_ALLOWED = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
}

_env_allowed = os.getenv("ALLOWED_ORIGINS", "").strip()
if _env_allowed:
    if _env_allowed == "*":
        ALLOWED_ORIGINS = None
    else:
        ALLOWED_ORIGINS = set([o.strip() for o in _env_allowed.split(",") if o.strip()])
else:
    ALLOWED_ORIGINS = _DEFAULT_ALLOWED


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False

    # If ALLOWED_ORIGINS is None, allow everything (explicit opt-in)
    if ALLOWED_ORIGINS is None:
        return True

    if origin in ALLOWED_ORIGINS:
        return True

    # Automatically allow Vercel production and preview domains
    if origin.endswith(".vercel.app") or "vercel.app" in origin:
        return True

    # Support wildcard patterns like https://*.example.com
    for allowed in ALLOWED_ORIGINS:
        if "*" in allowed:
            pattern = "^" + re.escape(allowed).replace(r"\*", ".*") + "$"
            if re.match(pattern, origin):
                return True

    # Dev convenience: allow localhost/127.0.0.1 on Vite ports (5173-5185)
    m = re.match(r"^https?://(localhost|127\.0\.0\.1):(\d+)$", origin)
    if not m:
        return False
    try:
        port = int(m.group(2))
    except Exception:
        return False
    return 5173 <= port <= 5185


@app.before_request
def handle_options_preflight():
    if request.method == "OPTIONS":
        origin = request.headers.get("Origin")
        if _is_allowed_origin(origin):
            resp = app.make_default_options_response()
            return resp


@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin")
    if _is_allowed_origin(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


def _issue_token(email, role):
    return _token_serializer.dumps({"email": email, "role": role})


def _verify_token(token):
    return _token_serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)


def require_auth(required_role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if request.method == "OPTIONS":
                return ("", 204)
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"message": "Missing token"}), 401
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = _verify_token(token)
            except SignatureExpired:
                return jsonify({"message": "Token expired"}), 401
            except BadSignature:
                return jsonify({"message": "Invalid token"}), 401

            if required_role and payload.get("role") != required_role:
                return jsonify({"message": "Forbidden"}), 403

            g.user = payload
            return fn(*args, **kwargs)

        return wrapper

    return decorator

# ==============================
# UTIL FUNCTIONS
# ==============================
def file_to_numpy(file_bytes):
    img = Image.open(io.BytesIO(file_bytes))

    # Pre-scale high-resolution images to max 640px.
    # DeepFace Facenet512 accepts 160x160 inputs; processing 2444x1718 or 4000x3000
    # images wastes CPU cycles, increases memory usage, and causes 30s+ timeouts on cloud CPUs.
    MAX_DIM = 640
    if max(img.size) > MAX_DIM:
        img.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)

    # If transparent PNG or paletted with alpha, composite onto clean white background
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[3])
        return np.array(bg)
    return np.array(img.convert("RGB"))


_model_lock = threading.Lock()
_model_ready = False
_model_warmup_error = None


def get_embedding(file_bytes, timeout_seconds=90):
    """
    Extracts a 512-d normalized embedding vector using DeepFace with cascading fallbacks:
    1. Primary detector with enforce_detection=True (detects actual face boundaries and facial features).
    2. Fallback to skip detector (uses the pre-scaled image directly, ideal for sketches, composites, and pre-cropped photos).
    Uses a bounded lock acquisition to prevent Gunicorn thread deadlocks.
    """
    acquired = _model_lock.acquire(timeout=timeout_seconds)
    if not acquired:
        print("[DeepFace] Warning: Lock acquisition timed out waiting for prior inference.")
        return None

    try:
        from deepface import DeepFace

        img = file_to_numpy(file_bytes)
        reps = None

        # 1. Primary detector (opencv or configured detector) with enforce_detection=True
        # When enforce_detection=True, if no face is found it raises an exception and cleanly falls back.
        detector_backend = DETECTOR if DETECTOR and DETECTOR != "skip" else "opencv"
        try:
            reps = DeepFace.represent(
                img_path=img,
                model_name=MODEL,
                detector_backend=detector_backend,
                enforce_detection=True,
            )
        except Exception as e:
            # Face not detected by primary detector
            reps = None

        # 2. Secondary fallback detector if primary was not opencv
        if not reps and detector_backend != "opencv":
            try:
                reps = DeepFace.represent(
                    img_path=img,
                    model_name=MODEL,
                    detector_backend="opencv",
                    enforce_detection=True,
                )
            except Exception:
                reps = None

        # 3. Third fallback: skip detector (handles composite sketches, drawings, and cropped face photos)
        if not reps:
            try:
                reps = DeepFace.represent(
                    img_path=img,
                    model_name=MODEL,
                    detector_backend="skip",
                    enforce_detection=False,
                )
            except Exception as e:
                print("DeepFace skip detector fallback error:", repr(e))
                reps = None

        if not reps or len(reps) == 0:
            print("[DeepFace] No representation extracted from image")
            return None

        emb = np.array(reps[0]["embedding"], dtype=np.float32)
        norm = float(np.linalg.norm(emb))
        if norm == 0 or np.isnan(norm):
            return None

        emb = emb / norm
        return emb.tolist()

    except Exception as e:
        print("Embedding extraction error:", repr(e))
        return None
    finally:
        _model_lock.release()


def _warmup_model():
    """Pre-warms TensorFlow and Facenet512 on worker startup."""
    global _model_ready, _model_warmup_error
    try:
        from deepface import DeepFace
        dummy = np.full((160, 160, 3), 255, dtype=np.uint8)
        with _model_lock:
            DeepFace.represent(img_path=dummy, model_name=MODEL, detector_backend="skip", enforce_detection=False)
        _model_ready = True
        print(f"[DeepFace] Model {MODEL} successfully pre-warmed and ready.")
    except Exception as e:
        _model_warmup_error = str(e)
        print("[DeepFace] Warmup notice:", repr(e))


threading.Thread(target=_warmup_model, daemon=True).start()


def upload_image(file_bytes):
    result = cloudinary.uploader.upload(io.BytesIO(file_bytes))
    return result["secure_url"]


def cosine_score(a, b):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0 or np.isnan(norm_a) or np.isnan(norm_b):
        return 0.0
    val = float(np.dot(a, b) / (norm_a * norm_b))
    return 0.0 if np.isnan(val) else val


# ==============================
# ROUTES
# ==============================
@app.route("/api/auth/signup", methods=["POST", "OPTIONS"])
def api_signup():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "NORMAL").strip().upper()
    admin_secret = data.get("adminSecret")

    if not name or not email or not password:
        return jsonify({"message": "Missing required fields"}), 400

    if role not in {"NORMAL", "ADMIN"}:
        return jsonify({"message": "Invalid role"}), 400

    if role == "ADMIN":
        required = os.getenv("ADMIN_SECRET_KEY")
        if not required:
            return (
                jsonify({"message": "Admin signup is not configured"}),
                400,
            )
        if admin_secret != required:
            return jsonify({"message": "Invalid admin secret"}), 403

    if users_collection.find_one({"email": email}):
        return jsonify({"message": "User already exists"}), 409

    users_collection.insert_one(
        {
            "name": name,
            "email": email,
            "passwordHash": generate_password_hash(password),
            "role": role,
            "createdAt": datetime.now(timezone.utc),
        }
    )

    return jsonify({"message": "Signup successful"}), 201


@app.route("/api/auth/login", methods=["POST", "OPTIONS"])
def api_login():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"message": "Missing email/password"}), 400

    user = users_collection.find_one({"email": email})
    if not user or not check_password_hash(user.get("passwordHash", ""), password):
        return jsonify({"message": "Invalid credentials"}), 401

    role = user.get("role") or "NORMAL"
    token = _issue_token(email=email, role=role)
    return jsonify({"token": token, "user": {"role": role}}), 200


@app.route("/api/upload", methods=["POST", "OPTIONS"])
@require_auth()
def api_upload_and_match():
    if request.method == "OPTIONS":
        return ("", 204)

    file = request.files.get("image")
    if not file:
        return jsonify({"error": "Please select an image"}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"error": "Uploaded image file is empty"}), 400

    query_emb = get_embedding(file_bytes)
    if query_emb is None:
        return (
            jsonify(
                {
                    "error": "Could not detect face features in the uploaded image. Please ensure the image shows a visible face, or try generating a clearer sketch."
                }
            ),
            400,
        )

    sex_filter = (request.form.get("sex_filter") or "").strip()
    mongo_query = {}
    if sex_filter and sex_filter.lower() != "any":
        mongo_query["sex"] = {"$regex": f"^{re.escape(sex_filter)}$", "$options": "i"}

    # Project only fields needed for results to minimize network payload
    projection = {
        "name": 1,
        "age": 1,
        "sex": 1,
        "crime": 1,
        "status": 1,
        "imageURL": 1,
        "embedding": 1,
    }

    docs = list(collection.find(mongo_query, projection))
    valid_docs = [d for d in docs if "embedding" in d and len(d["embedding"]) == 512]

    results = []
    top_candidates = []
    if valid_docs:
        q_vec = np.array(query_emb, dtype=np.float32)
        db_matrix = np.array([d["embedding"] for d in valid_docs], dtype=np.float32)

        # Vectorized cosine similarity: both q_vec and stored embeddings are already unit-normalized
        scores = np.dot(db_matrix, q_vec)

        for doc, score in zip(valid_docs, scores):
            sc = float(score)
            item = {
                "name": doc.get("name"),
                "age": doc.get("age"),
                "sex": doc.get("sex"),
                "crime": doc.get("crime"),
                "status": doc.get("status"),
                "imageURL": doc.get("imageURL"),
                "score": sc,
            }
            top_candidates.append(item)
            if sc >= THRESHOLD:
                results.append(item)

    results.sort(key=lambda x: x["score"], reverse=True)
    top_candidates.sort(key=lambda x: x["score"], reverse=True)

    has_strong_matches = len(results) > 0
    final_matches = results[:6] if has_strong_matches else top_candidates[:3]

    return jsonify({
        "matches": final_matches,
        "hasStrongMatches": has_strong_matches,
        "threshold": THRESHOLD,
        "totalCompared": len(valid_docs)
    }), 200


@app.route("/api/enroll", methods=["POST", "OPTIONS"])
@require_auth(required_role="ADMIN")
def api_enroll():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.form
    file = request.files.get("image")

    if not file:
        return jsonify({"message": "Upload image"}), 400

    file_bytes = file.read()

    embedding = get_embedding(file_bytes)
    if embedding is None:
        return (
            jsonify(
                {
                    "message": "Could not extract face features. If you just started the server, try again in 1–2 minutes. Otherwise use a clear, front-facing face image."
                }
            ),
            400,
        )

    image_url = upload_image(file_bytes)

    sex = (data.get("sex") or "").strip()
    status = (data.get("status") or "ARRESTED").strip()

    try:
        doc = {
            "name": data.get("name"),
            "age": int(data.get("age")),
            "sex": sex,
            "address": data.get("address"),
            "height": float(data.get("height")),
            "weight": float(data.get("weight")),
            "crime": data.get("crime"),
            "status": status,
            "imageURL": image_url,
            "embedding": embedding,
            "createdAt": datetime.now(timezone.utc),
        }
    except Exception:
        return jsonify({"message": "Invalid form fields"}), 400

    inserted = collection.insert_one(doc)
    return jsonify({"message": "Criminal added", "id": str(inserted.inserted_id)}), 201


@app.route("/api/members", methods=["GET", "OPTIONS"])
@require_auth()
def api_members_search():
    if request.method == "OPTIONS":
        return ("", 204)

    name = (request.args.get("name") or "").strip()
    sex = (request.args.get("sex") or "").strip()

    if not name:
        return jsonify({"message": "Missing name"}), 400

    mongo_query = {
        "name": {"$regex": re.escape(name), "$options": "i"}
    }

    if sex and sex.lower() != "any":
        mongo_query["sex"] = {"$regex": f"^{re.escape(sex)}$", "$options": "i"}

    members = []
    for doc in collection.find(mongo_query).sort("createdAt", -1).limit(25):
        members.append(
            {
                "name": doc.get("name"),
                "age": doc.get("age"),
                "sex": doc.get("sex"),
                "crime": doc.get("crime"),
                "status": doc.get("status"),
                "imageURL": doc.get("imageURL"),
            }
        )

    return jsonify({"members": members}), 200


@app.route("/api/latest-criminals", methods=["GET", "OPTIONS"])
def api_latest_criminals():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        limit = int(request.args.get("limit") or 10)
    except Exception:
        limit = 10

    limit = max(1, min(limit, 10))

    criminals = []

    # Home carousel: return random criminals that have an image.
    # (Optional) allow status filtering via ?status=NOT%20ARRESTED
    status = (request.args.get("status") or "").strip()

    mongo_match = {
        "imageURL": {"$exists": True, "$nin": [None, ""]},
    }
    if status:
        mongo_match["status"] = {"$regex": rf"^\s*{re.escape(status)}\s*$", "$options": "i"}

    pipeline = [
        {"$match": mongo_match},
        {"$sample": {"size": limit}},
    ]

    for doc in collection.aggregate(pipeline):
        criminals.append(
            {
                "name": doc.get("name"),
                "imageURL": doc.get("imageURL"),
                "sex": doc.get("sex"),
                "crime": doc.get("crime"),
                "status": doc.get("status"),
            }
        )

    return jsonify({"criminals": criminals}), 200


@app.route("/api/health", methods=["GET", "OPTIONS"])
def health_check():
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({
        "status": "healthy",
        "service": "FORENSIGHT Face Recognition API",
        "model": MODEL,
        "modelReady": _model_ready,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@app.get("/")
def index():
    try:
        return render_template("index.html", matches=None)
    except Exception:
        return jsonify({
            "status": "healthy",
            "service": "FORENSIGHT Face Recognition API",
            "message": "API is operational.",
            "healthCheck": "/api/health"
        }), 200


@app.post("/enroll")
def enroll():
    data = request.form

    admin_secret_required = os.getenv("ADMIN_SECRET_KEY")
    if not admin_secret_required:
        flash("❌ Enrollment disabled. Set ADMIN_SECRET_KEY in your .env to enable admin-only enrollment.", "error")
        return redirect(url_for("index"))

    provided_secret = (data.get("adminSecret") or "").strip()
    if provided_secret != admin_secret_required:
        flash("❌ Invalid admin secret key", "error")
        return redirect(url_for("index"))

    file = request.files.get("image")

    if not file:
        flash("Upload image", "error")
        return redirect(url_for("index"))

    file_bytes = file.read()

    embedding = get_embedding(file_bytes)
    if embedding is None:
        flash(
            "❌ Could not extract face features (try a clearer front-facing image)",
            "error",
        )
        return redirect(url_for("index"))

    image_url = upload_image(file_bytes)

    sex = (data.get("sex") or "").strip()
    status = (data.get("status") or "ARRESTED").strip()

    doc = {
        "name": data.get("name"),
        "age": int(data.get("age")),
        "sex": sex,
        "address": data.get("address"),
        "height": float(data.get("height")),
        "weight": float(data.get("weight")),
        "crime": data.get("crime"),
        "status": status,
        "imageURL": image_url,
        "embedding": embedding,
        "createdAt": datetime.now(timezone.utc)
    }

    collection.insert_one(doc)

    flash("✅ Criminal added", "success")
    return redirect(url_for("index"))


@app.post("/search")
def search():
    file = request.files.get("image")
    sex_filter = (request.form.get("sex_filter") or "").strip()

    if not file:
        flash("Upload image", "error")
        return redirect(url_for("index"))

    file_bytes = file.read()

    query_emb = get_embedding(file_bytes)
    if query_emb is None:
        flash(
            "❌ Could not extract face features (try a clearer front-facing image)",
            "error",
        )
        return redirect(url_for("index"))

    results = []

    mongo_query = {}
    if sex_filter and sex_filter.lower() != "any":
        mongo_query["sex"] = {"$regex": f"^{re.escape(sex_filter)}$", "$options": "i"}

    for doc in collection.find(mongo_query):
        if "embedding" not in doc:
            continue

        score = cosine_score(query_emb, doc["embedding"])

        if score >= THRESHOLD:
            results.append({
                "name": doc["name"],
                "age": doc["age"],
                "sex": doc["sex"],
                "crime": doc["crime"],
                "status": doc["status"],
                "imageURL": doc["imageURL"],
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    if results:
        flash(f"✅ {len(results)} matches found", "success")
    else:
        flash("❌ No matches", "warning")

    try:
        return render_template("index.html", matches=results[:6])
    except Exception:
        return jsonify({"matches": results[:6]}), 200


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    app.run(debug=True, port=8000, use_reloader=False)