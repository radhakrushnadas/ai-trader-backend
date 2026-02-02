# ----------------------------
# Optimized Dockerfile for ai-trader-backend
# ----------------------------

# Stage 1: Build stage
FROM python:3.11-slim AS build

# Set working directory
WORKDIR /app

# Install build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages in build stage
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --prefix=/install -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim

WORKDIR /app

# Copy only installed packages from build stage
COPY --from=build /install /usr/local

# Copy application code
COPY . .

# Expose port for Uvicorn
EXPOSE 8000

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
