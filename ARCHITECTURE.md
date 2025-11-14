# Email Classifier Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Email Classifier Container                   │
│                                                                   │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Web UI     │      │   SMTP       │      │   Trainer    │  │
│  │   (Flask)    │      │   Server     │      │   Service    │  │
│  │   Port 8080  │      │   Port 2525  │      │   (Thread)   │  │
│  └──────┬───────┘      └──────┬───────┘      └──────┬───────┘  │
│         │                     │                      │           │
│         │                     │                      │           │
│         │              ┌──────▼──────────────────────▼────────┐ │
│         │              │                                       │ │
│         │              │    DistilBERT Classifier              │ │
│         │              │    (EmailClassifier class)            │ │
│         │              │                                       │ │
│         │              │  - Extract features (embeddings)      │ │
│         │              │  - Logistic regression classifier     │ │
│         │              │  - Apply user weights                 │ │
│         │              │                                       │ │
│         │              └───────────┬───────────────────────────┘ │
│         │                          │                             │
│         └──────────────────────────┼─────────────────────────────┤
│                                    │                             │
│                           ┌────────▼─────────┐                   │
│                           │   SQLite DB      │                   │
│                           │  - Classifications│                   │
│                           │  - Training Data │                   │
│                           │  - User Prefs    │                   │
│                           └──────────────────┘                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
           ▲                        │                      │
           │                        │                      │
           │                        ▼                      ▼
    ┌──────┴──────┐        ┌──────────────┐      ┌──────────────┐
    │   Browser   │        │  Fetchmail/  │      │  IMAP Server │
    │             │        │  Postfix     │      │              │
    └─────────────┘        └──────────────┘      └──────────────┘
```

## Data Flow

### 1. Email Classification Flow

```
Incoming Email
    │
    ▼
Fetchmail (retrieves from remote IMAP)
    │
    ▼
Classifier SMTP Server (port 2525)
    │
    ├─ Parse email (subject + body)
    │
    ├─ Extract DistilBERT features (768-dim embedding)
    │
    ├─ Apply logistic regression
    │
    ├─ Apply user weights
    │
    ├─ Add X-Email-Category header
    │
    ├─ Log to database
    │
    ▼
Local delivery (sendmail/LMTP)
```

### 2. Training Flow

```
Initial Training:
    │
    ├─ Connect to IMAP (for each user)
    │
    ├─ Read from INBOX → "personal" labels
    │
    ├─ Read from Shopping → "shopping" labels
    │
    ├─ Read from Junk → "spam" labels
    │
    ├─ Extract features for all emails
    │
    ├─ Train logistic regression on DistilBERT embeddings
    │
    ▼
Save model

Continuous Learning:
    │
    ├─ Every TRAINING_INTERVAL seconds
    │
    ├─ Check current folder location for known emails
    │
    ├─ Detect if email moved to different folder
    │
    ├─ Update training_data table with new category
    │
    ├─ Retrain model with updated data
    │
    ▼
Save updated model
```

### 3. Dashboard Flow

```
User opens http://localhost:8080
    │
    ▼
Flask queries SQLite database
    │
    ├─ Get classification stats
    │
    ├─ Get recent 50 classifications
    │
    ├─ Get training data distribution
    │
    ▼
Render HTML dashboard
    │
    ▼
Auto-refresh every 30 seconds
```

## Component Details

### DistilBERT (66M parameters)
- Transformer-based model (distilled from BERT)
- Converts text → 768-dimensional embedding
- Pre-trained on English corpus
- Fast inference (~0.1s per email)

### Logistic Regression Layer
- Multi-class classification (3 categories)
- Trained on DistilBERT embeddings
- Outputs probability distribution
- Fast training (~1min for 300 emails)

### User Weights
- Per-user preference multipliers
- Adjusts category probabilities
- Learned from folder movements
- Allows personalization

## Database Schema

```sql
-- Track all classifications
classifications:
  - id (PK)
  - message_id
  - user_email
  - subject
  - predicted_category
  - confidence
  - actual_category (NULL until verified)
  - processing_time
  - timestamp

-- Training data from IMAP
training_data:
  - id (PK)
  - message_id (UNIQUE)
  - user_email
  - subject
  - body
  - category
  - timestamp

-- Per-user preferences
user_preferences:
  - user_email (PK)
  - personal_weight
  - shopping_weight
  - spam_weight
```

## Performance Characteristics

### Latency
- Feature extraction: ~80-100ms
- Classification: ~10-20ms
- Total: ~100-150ms per email

### Training
- Initial training (300 emails): ~1-2 minutes
- Incremental retraining: ~30-60 seconds

### Memory
- DistilBERT model: ~260MB
- Python runtime: ~500MB
- SQLite database: ~10MB per 10k emails
- Total: ~2GB RAM

### Storage
- DistilBERT model: ~260MB
- Trained classifier: ~10MB
- Database: grows with usage
- Recommended: 1GB free space

## Deployment Notes

### Docker Networks
- Joins `mailserver-network` to communicate with docker-mailserver
- Exposes port 8080 (web UI) and 2525 (SMTP)

### Volumes
- `/app/data` → persistent database and logs
- `/app/models` → trained model persistence

### Environment Variables
- Configure via .env file
- Supports multiple IMAP users
- Adjustable training interval
- Configurable confidence threshold
