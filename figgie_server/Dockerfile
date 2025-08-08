# Dockerfile for FiggieServer backend
FROM python:3.13-slim

# Set work directory
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

COPY figgie_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY figgie_server ./figgie_server

# Expose port
EXPOSE 5000

# Run the server
CMD ["python", "-m", "figgie_server.wsgi"]
