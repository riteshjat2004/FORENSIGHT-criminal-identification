FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system deps required by OpenCV / Pillow and DeepFace backends
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r /app/requirements.txt

# Pre-download and cache Facenet512 weights during image build so startup is instant
RUN python -c "from deepface import DeepFace; import numpy as np; DeepFace.represent(img_path=np.full((160,160,3),255,dtype=np.uint8), model_name='Facenet512', detector_backend='skip', enforce_detection=False)"

# Copy application
COPY . /app

EXPOSE 8000

# Use gunicorn for production with dynamic $PORT binding and timeout for deepface
CMD ["sh", "-c", "gunicorn app:app -b 0.0.0.0:${PORT:-8000} -w 1 --threads 2 --timeout 180"]
