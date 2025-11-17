# Email Classifier with Local LLM

A Docker-based email classification system using DistilBERT that learns from user behavior to automatically categorize emails into Personal, Shopping, or Spam folders.

## Features

- **Local LLM Classification**: Uses DistilBERT for privacy-focused, on-premise email classification
- **Lightweight CPU-Only PyTorch**: Optimized for CPU inference (~140MB download vs 670MB CUDA version)
- **Continuous Learning**: Monitors IMAP folders and retrains when users move emails
- **Per-User Preferences**: Weights classifications based on individual user behavior
- **Web Dashboard**: Real-time monitoring of classifications, stats, and training data
- **SMTP Integration**: Receives emails via SMTP for classification before delivery
- **Docker-Based**: Easy deployment alongside docker-mailserver

## Quick Start

### 1. Configure Environment

Create a `.env` file:

```bash
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USERS=user1@example.com:password1,user2@example.com:password2
TRAINING_INTERVAL=3600
CONFIDENCE_THRESHOLD=0.7
```

**✨ Optimized for CPU**: This project uses PyTorch CPU-only version, which is much smaller (~140MB vs 670MB) and perfectly adequate for email classification. No GPU required!

### 2. Build

Use the provided build script for an easy build process:

```bash
chmod +x build.sh
./build.sh
```

Or build manually:

```bash
docker build -t email-classifier .
```

For slow networks, use the layered build:
```bash
docker build -f Dockerfile.layered -t email-classifier .
```

### 3. Create Docker Network

```bash
docker network create mailserver-network
```

### 4. Build and Run

```bash
docker-compose up -d
```

### 5. Access Dashboard

Open http://localhost:8080 to view the classification dashboard.

## Integration with docker-mailserver

The classifier acts as an SMTP relay - it receives emails, classifies them, adds headers, and forwards to your docker-mailserver. **No sendmail binary required!**

### Via Fetchmail (Recommended)

Update your fetchmail config to route through the classifier:

```conf
poll imap.gmail.com with proto IMAP
   user 'youruser' there with password 'yourpass' ssl
   is 'localuser' here
   smtphost localhost/2525  # Route to classifier
   keep
   no fetchall
   no rewrite
   idle
```

The classifier will classify, add headers, and forward to docker-mailserver via SMTP.

**See [DOCKER_MAILSERVER.md](DOCKER_MAILSERVER.md) for complete docker-mailserver integration.**  
**See [FETCHMAIL_UPDATE.md](FETCHMAIL_UPDATE.md) for quick fetchmail setup.**

### Configuration

```bash
# .env
DELIVERY_HOST=mailserver  # Your docker-mailserver container name
DELIVERY_PORT=25          # DMS SMTP port
```

### Via Postfix

Add to Postfix main.cf:

```
content_filter = classifier:localhost:2525
```

## Architecture

```
Fetchmail → Classifier (port 2525) → Classification → Delivery
                ↓
          Training Loop (checks IMAP every hour)
                ↓
          Retrain Model
```

### Components

- **SMTP Server** (port 2525): Receives emails, classifies, adds headers
- **Training Service**: Monitors IMAP folders, detects reclassifications, retrains model
- **Web UI** (port 8080): Dashboard showing stats and recent classifications
- **DistilBERT Model**: Lightweight transformer for text classification

## Email Classification

The classifier adds headers to each email:

```
X-Email-Category: shopping
X-Classification-Confidence: 0.85
```

These can be used by your mail server for filtering/routing.

## Training Process

### Initial Training

1. Connects to IMAP for each configured user
2. Reads last 100 messages from each folder (INBOX, Shopping, Junk)
3. Extracts text and trains DistilBERT classifier
4. Saves model to `/app/models/classifier.pkl`

### Continuous Learning

1. Every hour (configurable), checks IMAP folders
2. Detects if messages have been moved to different folders
3. Updates training data with new classifications
4. Retrains model with updated data

### User Preferences

The system learns per-user classification preferences. If a user frequently moves shopping emails to inbox, the classifier weights those signals for that user.

## Data Storage

All data stored in `/app/data`:

- `classifier.db`: SQLite database with classifications and training data
- `/app/models/classifier.pkl`: Trained model

## Configuration

### Environment Variables

- `IMAP_HOST`: IMAP server hostname
- `IMAP_PORT`: IMAP port (default: 993)
- `IMAP_USERS`: Comma-separated list of user:password pairs
- `TRAINING_INTERVAL`: Seconds between retraining checks (default: 3600)
- `TRAINING_SCHEDULE`: Daily training time in HH:MM format (default: "3:00")
- `CONFIDENCE_THRESHOLD`: Minimum confidence for classification (default: 0.7)
- `MAX_TRAINING_EMAILS`: Maximum emails per folder for initial training (default: 500)
- `MAX_TOTAL_TRAINING_MESSAGES`: Maximum total messages in training database (default: 10000)
- `MAX_TRAINING_TIME_SECONDS`: Maximum time allowed for model training (default: 300)

### Volumes

Mount these for persistence:

```yaml
volumes:
  - ./data:/app/data      # Database and training data
  - ./models:/app/models  # Trained models
```

## API Endpoints

- `GET /` - Web dashboard
- `GET /api/stats` - JSON stats endpoint

## Requirements

- Docker & Docker Compose
- 1.5-2GB RAM (CPU-only PyTorch is memory efficient)
- ~2GB disk space (for images and data)
- Network access to IMAP server
- No GPU required - optimized for CPU inference

## Email Folder Structure

The classifier expects these IMAP folders:

- `INBOX` → personal category
- `Shopping` → shopping category
- `Junk` → spam category

Create these folders in your mail client if they don't exist.

## Monitoring

The web dashboard shows:

- Total emails processed
- Category distribution
- Average processing time
- Training data count
- Recent classifications (last 50)
- Per-user training data distribution

## Performance

- Initial model training: ~1-2 minutes (300 emails)
- Classification time: ~0.1-0.3 seconds per email (CPU-only)
- PyTorch package size: ~140MB (CPU-only version)
- DistilBERT model size: ~260MB
- Total Docker image: ~1.2GB
- Retraining: ~1-2 minutes (depends on dataset size)
- Memory usage: ~1.5-2GB RAM

**CPU Performance**: The CPU-only version is optimized for inference and provides excellent performance for email classification without requiring GPU resources.

## Troubleshooting

### Build timeout during pip install

If the Docker build times out while downloading packages, try:

```bash
# Build with increased timeout
DOCKER_BUILDKIT=1 docker-compose build --build-arg BUILDKIT_STEP_LOG_MAX_SIZE=50000000

# Or build directly with timeout
docker build --network=host -t email-classifier --build-arg PIP_DEFAULT_TIMEOUT=300 .
```

Alternatively, you can build the image on a machine with better network connectivity and export/import it.

### No training data

Ensure IMAP credentials are correct and folders exist with messages.

### Low accuracy

- Add more training emails (100+ per category recommended)
- Check that folders are correctly named
- Verify messages are distributed across categories

### SMTP connection issues

Ensure port 2525 is accessible and not blocked by firewall.

## Security Notes

- IMAP credentials stored in environment variables
- Consider using secrets management for production
- All processing happens locally - no data leaves your server
- Model and training data stored in mounted volumes

## License

MIT
