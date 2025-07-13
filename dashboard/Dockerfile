# Dockerfile for the Dash-based Figgie dashboard
FROM python:3.13-alpine

# Set working directory
WORKDIR /app
ENV PYTHONPATH=/app

# Install dependencies
RUN pip install --no-cache-dir dash pandas plotly psycopg-binary psycopg

# Copy application code
COPY dashboard ./dashboard
COPY figgie_server ./figgie_server

# Expose Dash default port
EXPOSE 8050

# Launch dashboard server
CMD ["python", "dashboard/app.py"]
