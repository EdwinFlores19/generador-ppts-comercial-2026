FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R app:app /app

USER app

EXPOSE 5000

# Un solo worker con hilos: el rate limiter y la caché del Estimador
# viven en memoria de proceso (dict/threading.Lock), por lo que con
# --workers > 1 cada proceso tendría su propio estado y el límite de
# peticiones y la caché dejarían de ser consistentes entre workers.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
