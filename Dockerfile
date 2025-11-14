FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel for faster builds
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy requirements
COPY requirements.txt .

# Install dependencies with increased timeout and retries
# The --extra-index-url in requirements.txt will ensure CPU-only PyTorch (~140MB instead of 670MB)
RUN pip install --no-cache-dir \
    --default-timeout=300 \
    --retries 10 \
    -r requirements.txt

# Download DistilBERT model at build time
RUN python -c "from transformers import AutoTokenizer, AutoModel; \
    print('Downloading DistilBERT tokenizer...'); \
    AutoTokenizer.from_pretrained('distilbert-base-uncased'); \
    print('Downloading DistilBERT model...'); \
    AutoModel.from_pretrained('distilbert-base-uncased'); \
    print('Model ready!')"

# Copy application code
COPY *.py .

# Create necessary directories
RUN mkdir -p /app/data /app/models

EXPOSE 8080 2525

CMD ["python", "main.py"]
