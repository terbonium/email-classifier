FROM python:3.11-slim

# Build argument to specify branch/tag (defaults to main)
ARG GIT_BRANCH=main
ARG REPO_URL=https://github.com/terbonium/email-classifier.git

WORKDIR /app

# Install system dependencies including git
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel for faster builds
RUN pip install --no-cache-dir --upgrade pip wheel

# Clone the repository
RUN git clone --depth 1 --branch ${GIT_BRANCH} ${REPO_URL} /tmp/repo && \
    cp -r /tmp/repo/* /app/ && \
    rm -rf /tmp/repo

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

# Create necessary directories
RUN mkdir -p /app/data /app/models

EXPOSE 8080 2525

CMD ["python", "main.py"]
