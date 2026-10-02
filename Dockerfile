FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=main:app
ENV FLASK_DEBUG=0

WORKDIR /app/backend/app

RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/app/ .
COPY frontend/ /app/frontend/
COPY VERSION /app/VERSION

EXPOSE 8080

CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
