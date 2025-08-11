# Dockerfile for the Dash-based Figgie dashboard
FROM python:3.13-slim

# Set working directory
WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY dashboard ./dashboard
COPY figgie_server/db.py ./figgie_server/db.py
COPY agents ./agents

# Expose Dash default port
EXPOSE 8050

# Launch dashboard server
CMD ["python", "dashboard/app.py"]
