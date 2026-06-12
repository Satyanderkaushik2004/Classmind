FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Java JDK, Go, GCC, G++, and Node.js)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk \
    golang \
    gcc \
    g++ \
    nodejs \
    && rm -rf /var/lib/apt/lists/*



# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port 8080 (Google Cloud Run default)
EXPOSE 8080

# Run the application (dynamic port binding for Render/Cloud Run)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}


