#!/bin/bash

# Azure App Service startup script
# This script ensures the Python application starts correctly

echo "Starting PGS Call Translate application..."

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    echo "Using existing virtual environment..."
    source venv/bin/activate
fi

# Start the application
echo "Starting FastAPI application with uvicorn..."
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1