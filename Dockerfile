FROM python:3.11-slim

WORKDIR /app

# Pinned versions match requirements.txt for the Firestore-backed
# pricing-config editor (src/main.py routes /api/pricing-config).
RUN pip install --no-cache-dir \
    flask==3.1.* \
    gunicorn==23.* \
    google-cloud-firestore==2.19.*

COPY src/ ./src/
COPY shared/ ./shared/
COPY docs/forms/ ./docs/forms/
COPY vinci-catalog/web-app/public/ ./vinci-catalog/web-app/public/

EXPOSE 8080

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--chdir", "src", "main:app"]
