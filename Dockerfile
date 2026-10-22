FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATA_DIR=/data PORT=8000
VOLUME ["/data"]
EXPOSE 8000
CMD ["gunicorn","-c","gunicorn.conf.py","wsgi:app"]