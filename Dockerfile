# Use Python 3.13 base image
FROM python:3.13-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your app
COPY . .

# Command to run your app (adjust 'main:app' if needed)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
