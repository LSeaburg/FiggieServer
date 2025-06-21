# Dockerfile for FiggieServer backend
FROM python:3.13-alpine

# Set work directory
WORKDIR /app

RUN pip install --no-cache-dir flask psycopg-binary psycopg

# Copy application code
COPY figgie_server ./figgie_server

# Expose port
EXPOSE 8000

# Run the server
CMD ["python", "-m", "figgie_server.api"]
