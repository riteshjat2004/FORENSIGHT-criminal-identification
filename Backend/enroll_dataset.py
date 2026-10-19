import io
import os
import re
import sys
import numpy as np
from datetime import datetime, timezone
import hashlib
from dotenv import load_dotenv
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
from deepface import DeepFace

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")
if not MONGO_URI:
    print("Error: MONGO_CONNECTION_STRING is not set in .env")
    sys.exit(1)

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client["face_recognition_db"]
collection = db["criminals"]

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

MODEL = os.getenv("FACE_MODEL", "Facenet512")
DETECTOR = os.getenv("FACE_DETECTOR", "retinaface")

# Realistic names
MALE_FIRST_NAMES = [
    "Aarav", "Kabir", "Rohan", "Vikram", "Aditya", "Sameer", "Rajesh", "Kunal",
    "Manish", "Gaurav", "Suresh", "Nikhil", "Deepak", "Vivek", "Alok", "Varun",
    "Pradeep", "Sachin", "Abhishek", "Karan", "Suraj", "Amit", "Rahul", "Dinesh",
    "Sunil", "Ajay", "Devendra", "Pawan", "Hemant", "Harish", "Tarun", "Arun",
    "Ashish", "Mohit", "Pankaj", "Vikas"
]

FEMALE_FIRST_NAMES = [
    "Pooja", "Ananya", "Rhea", "Kavita", "Sneha", "Divya", "Priya", "Sunita",
    "Meera", "Swati", "Neha", "Ritu", "Deepika", "Shreya", "Simran", "Tanya",
    "Aarti", "Bhavna", "Poonam", "Komal", "Geeta", "Jyoti", "Rekha"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Singh", "Yadav", "Mishra", "Chauhan",
    "Rao", "Joshi", "Deshmukh", "Mehta", "Malhotra", "Kapoor", "Bhatia", "Reddy",
    "Nair", "Saxena", "Trivedi", "Pandey", "Dubey", "Shukla", "Chopra", "Kashyap",
    "Aggarwal", "Rawat", "Goswami", "Thakur", "Rathore", "Pawar"
]

CITIES = [
    ("42 Park Street", "Kolkata, WB"),
    ("15 MG Road", "Bengaluru, KA"),
    ("88 Link Road, Andheri West", "Mumbai, MH"),
    ("104 Civil Lines", "Jaipur, RJ"),
    ("23 Hazratganj", "Lucknow, UP"),
    ("74 Arera Colony", "Bhopal, MP"),
    ("19 FC Road, Shivajinagar", "Pune, MH"),
    ("51 CG Road, Navrangpura", "Ahmedabad, GJ"),
    ("36 Banjara Hills", "Hyderabad, TG"),
    ("12 Sector 17", "Chandigarh, CH"),
    ("63 Connaught Place", "New Delhi, DL"),
    ("9 Rajpur Road", "Dehradun, UK"),
    ("27 South Extension", "New Delhi, DL"),
    ("55 VIP Road", "Surat, GJ"),
]

CRIMES = [
    "Cyber Fraud & Phishing",
    "Armed Robbery",
    "Commercial Burglary",
    "Identity Theft & Forgery",
    "Extortion & Blackmail",
    "Money Laundering",
    "Smuggling of Contraband",
    "Bank Heist & Wire Fraud",
    "Credit Card Counterfeiting",
    "Corporate Data Espionage",
    "Vehicle Theft Syndicate",
    "High-Value Securities Fraud",
]

def generate_profile(filename: str):
    """Deterministically generates a realistic criminal profile based on the filename hash."""
    h = int(hashlib.md5(filename.encode("utf-8")).hexdigest(), 16)
    
    is_female = filename.startswith("CFD-IF")
    sex = "Female" if is_female else "Male"
    
    if is_female:
        first_name = FEMALE_FIRST_NAMES[h % len(FEMALE_FIRST_NAMES)]
        height = round(152.0 + (h % 22) + ((h // 10) % 10) * 0.1, 1)  # 152.0 - 174.0
        weight = round(48.0 + (h % 25) + ((h // 7) % 10) * 0.1, 1)    # 48.0 - 73.0
    else:
        first_name = MALE_FIRST_NAMES[h % len(MALE_FIRST_NAMES)]
        height = round(164.0 + (h % 25) + ((h // 10) % 10) * 0.1, 1)  # 164.0 - 189.0
        weight = round(60.0 + (h % 32) + ((h // 7) % 10) * 0.1, 1)    # 60.0 - 92.0
        
    last_name = LAST_NAMES[(h // 5) % len(LAST_NAMES)]
    full_name = f"{first_name} {last_name}"
    
    age = 22 + (h % 36) # 22 to 57
    
    street, city = CITIES[(h // 11) % len(CITIES)]
    address = f"{street}, {city}"
    
    crime = CRIMES[(h // 13) % len(CRIMES)]
    # ~60% Arrested, 40% Not Arrested
    status = "ARRESTED" if (h % 10) < 6 else "NOT ARRESTED"
    
    return {
        "name": full_name,
        "age": age,
        "sex": sex,
        "address": address,
        "height": height,
        "weight": weight,
        "crime": crime,
        "status": status,
    }


def extract_face_embedding(image_path: str):
    """Extracts a 512-d normalized embedding vector using DeepFace with fallback."""
    reps = None
    # 1. Primary configured detector
    try:
        reps = DeepFace.represent(
            img_path=image_path,
            model_name=MODEL,
            detector_backend=DETECTOR,
            enforce_detection=False,
        )
    except Exception as e:
        print(f"  [Primary {DETECTOR} detector failed: {e}] - trying fallback...")

    # 2. Fallback to opencv detector
    if not reps:
        try:
            reps = DeepFace.represent(
                img_path=image_path,
                model_name=MODEL,
                detector_backend="opencv",
                enforce_detection=False,
            )
        except Exception as e:
            print(f"  [OpenCV detector failed: {e}]")
            return None

    if not reps or len(reps) == 0:
        return None

    emb = np.array(reps[0]["embedding"], dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    if norm == 0 or np.isnan(norm):
        return None
    emb = emb / norm
    return emb.tolist()


def upload_to_cloudinary(image_path: str, public_id: str):
    """Uploads image file to Cloudinary under the forensight_criminals folder."""
    result = cloudinary.uploader.upload(
        image_path,
        folder="forensight_criminals",
        public_id=public_id,
        overwrite=True,
        resource_type="image",
    )
    return result["secure_url"]


def main():
    faces_dir = os.path.join(os.path.dirname(BASE_DIR), "faces")
    if not os.path.isdir(faces_dir):
        # Fallback to local faces dir if running inside project
        faces_dir = os.path.abspath("faces")

    print(f"Scanning images from: {faces_dir}")
    if not os.path.isdir(faces_dir):
        print(f"Error: Directory {faces_dir} not found.")
        sys.exit(1)

    files = sorted([f for f in os.listdir(faces_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    total = len(files)
    print(f"Found {total} face images to process.\n")

    enrolled_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, filename in enumerate(files, 1):
        image_path = os.path.join(faces_dir, filename)
        clean_stem = os.path.splitext(filename)[0].lower().replace("-", "_")

        # Check if already enrolled
        existing = collection.find_one({"sourceFile": filename})
        if existing:
            print(f"[{idx}/{total}] Skipping {filename} (already in DB: {existing.get('name')})", flush=True)
            skipped_count += 1
            continue

        print(f"[{idx}/{total}] Processing {filename}...", flush=True)
        
        # 1. Profile metadata
        profile = generate_profile(filename)
        
        # 2. Face embedding
        emb = extract_face_embedding(image_path)
        if emb is None:
            print(f"  [ERROR] Failed to extract embedding for {filename}. Skipping.", flush=True)
            failed_count += 1
            continue
            
        # 3. Cloudinary upload
        try:
            cloud_url = upload_to_cloudinary(image_path, clean_stem)
        except Exception as e:
            print(f"  [ERROR] Cloudinary upload error for {filename}: {e}", flush=True)
            failed_count += 1
            continue

        # 4. Save to MongoDB
        doc = {
            "name": profile["name"],
            "age": profile["age"],
            "sex": profile["sex"],
            "address": profile["address"],
            "height": profile["height"],
            "weight": profile["weight"],
            "crime": profile["crime"],
            "status": profile["status"],
            "imageURL": cloud_url,
            "embedding": emb,
            "sourceFile": filename,
            "createdAt": datetime.now(timezone.utc),
        }

        inserted = collection.insert_one(doc)
        enrolled_count += 1
        print(
            f"  [OK] Enrolled: {profile['name']} | {profile['sex']} | Age: {profile['age']} | "
            f"{profile['status']} | Crime: {profile['crime']}",
            flush=True,
        )
        print(f"       CDN: {cloud_url}", flush=True)

    print("\n========================================", flush=True)
    print("ENROLLMENT SUMMARY", flush=True)
    print(f"Total Images: {total}", flush=True)
    print(f"Enrolled New: {enrolled_count}", flush=True)
    print(f"Skipped (Already Present): {skipped_count}", flush=True)
    print(f"Failed: {failed_count}", flush=True)
    print(f"Total in Database: {collection.count_documents({})}", flush=True)
    print("========================================", flush=True)


if __name__ == "__main__":
    main()
