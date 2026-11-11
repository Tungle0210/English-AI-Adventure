FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.lock.txt backend/requirements.lock.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt
COPY backend backend
COPY scripts/phase1.py scripts/phase1.py
COPY scripts/start-production.py scripts/start-production.py
COPY scripts/data_bundle.py scripts/data_bundle.py
CMD ["python", "scripts/start-production.py"]
