# Email Classifier - Quick Start Guide

## What You're Getting

A complete Docker-based email classification system that:
- Uses DistilBERT (local LLM) to classify emails into Personal, Shopping, or Spam
- Learns from your behavior by monitoring when you move emails between folders
- Integrates with docker-mailserver via SMTP
- Provides a web dashboard for monitoring

## Files Included

```
email-classifier/
├── Dockerfile              # Container build instructions
├── docker-compose.yml      # Service orchestration
├── requirements.txt        # Python dependencies
├── main.py                # Main entry point
├── classifier.py          # DistilBERT classification engine
├── trainer.py             # IMAP monitoring and retraining
├── smtp_server.py         # SMTP server for email intake
├── web_ui.py              # Flask dashboard
├── config.py              # Configuration and database
├── test_classifier.py     # Testing script
├── .env.example           # Environment template
├── .gitignore            # Git ignore rules
└── README.md             # Full documentation
```

## Setup in 3 Steps

### 1. Configure

```bash
cd email-classifier
cp .env.example .env
# Edit .env with your IMAP credentials
```

**Note**: Uses PyTorch CPU-only (~140MB) - no GPU needed! Perfect for email classification.

### 2. Build & Deploy

Option A - Use the build script (recommended):
```bash
chmod +x build.sh
./build.sh
```

Option B - Manual build and deploy:
```bash
# Create shared network with docker-mailserver
docker network create mailserver-network

# Build and start the classifier
docker-compose up -d
```

**If build times out**, the build script offers a layered option that installs packages separately, making it more resilient to network issues.

### 3. Monitor

Open http://localhost:8080 to see the dashboard.

## How It Works

### Initial Training
1. Connects to your IMAP server
2. Reads existing emails from INBOX, Shopping, and Junk folders
3. Trains DistilBERT model on your email patterns
4. Ready to classify new emails

### Email Classification
1. Email arrives via fetchmail → classifier SMTP (port 2525)
2. DistilBERT analyzes subject + body
3. Adds classification headers (X-Email-Category, X-Classification-Confidence)
4. Forwards to local delivery

### Continuous Learning
1. Every hour, checks if you moved emails between folders
2. Updates training data with your corrections
3. Retrains model to learn your preferences
4. Adapts classification to match your behavior

## Integration with docker-mailserver

### Via Fetchmail

Add to your fetchmail config:
```
poll mail.provider.com protocol IMAP
  user "you@example.com" password "yourpass"
  smtphost localhost:2525
  no keep
```

### Via Postfix

Add to main.cf:
```
content_filter = classifier:localhost:2525
```

## Testing

Send test emails:
```bash
docker exec -it email-classifier python test_classifier.py
```

Check the dashboard to see classifications.

## Key Features

- **Privacy**: All processing happens locally, no data sent to cloud
- **Learning**: Adapts to your classification preferences over time
- **Fast**: ~0.1-0.3 seconds per email
- **Lightweight**: DistilBERT is only 260MB
- **Per-User**: Learns preferences for each configured user
- **Monitoring**: Real-time dashboard with stats and recent classifications

## Folder Requirements

Ensure these IMAP folders exist:
- INBOX (for personal emails)
- Shopping (for shopping/promotional emails)
- Junk (for spam)

## Resource Usage

- RAM: ~2GB
- Storage: ~500MB (model + data)
- CPU: Minimal (classification is fast)

## Next Steps

1. Let it train on your existing emails (takes 1-2 minutes)
2. Configure fetchmail or postfix to route through classifier
3. Use email normally - classifier learns from your actions
4. Check dashboard to monitor performance

## Troubleshooting

**No classifications appearing?**
- Check SMTP is accessible: `telnet localhost 2525`
- Verify IMAP credentials in .env
- Check logs: `docker-compose logs -f`

**Low accuracy?**
- Ensure 100+ emails per category for good training
- Check folder names match (INBOX, Shopping, Junk)
- Give it time to learn from your behavior

**Want to retrain from scratch?**
```bash
docker-compose down
rm -rf data/ models/
docker-compose up -d
```

## Support

See README.md for detailed documentation.
