# Fetchmail Integration Guide

This guide shows how to integrate the email classifier with your existing fetchmail setup.

## Your Current Setup

```conf
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   mda "/usr/local/bin/classify-and-log.sh | /usr/sbin/sendmail -i -f %F -- %T"
   keep
   no fetchall
   no rewrite
   idle
```

## Option 1: Direct SMTP Route (Recommended)

Replace the MDA with direct SMTP delivery to the classifier:

```conf
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   smtphost localhost/2525
   keep
   no fetchall
   no rewrite
   idle
```

**How it works:**
```
Gmail → Fetchmail → Classifier (port 2525) → Sendmail → Mailbox
                         ↓
                   Adds headers:
                   X-Email-Category
                   X-Classification-Confidence
```

**Advantages:**
- Cleaner setup
- Classifier handles delivery
- Full email preserved
- Better error handling

## Option 2: Keep Your Script (Pipe Through)

Keep your existing script and pipe through the classifier:

### Update classify-and-log.sh

```bash
#!/bin/bash
# classify-and-log.sh - Updated to use email classifier

# Read the email from stdin
EMAIL=$(cat)

# Send to classifier via SMTP and capture response with headers
CLASSIFIED=$(echo "$EMAIL" | curl -s --upload-file - \
  smtp://localhost:2525 \
  --mail-from "$1" \
  --mail-rcpt "$2" \
  -w "\n%{http_code}")

# Extract classification from headers
CATEGORY=$(echo "$CLASSIFIED" | grep -i "^X-Email-Category:" | cut -d' ' -f2)
CONFIDENCE=$(echo "$CLASSIFIED" | grep -i "^X-Classification-Confidence:" | cut -d' ' -f2)

# Log to your existing log
echo "$(date): $CATEGORY ($CONFIDENCE) - Subject: $3" >> /var/log/email-classifier.log

# Pass through to sendmail
echo "$CLASSIFIED"
```

**Fetchmail config:**
```conf
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   mda "/usr/local/bin/classify-and-log.sh %F %T '%s' | /usr/sbin/sendmail -i -f %F -- %T"
   keep
   no fetchall
   no rewrite
   idle
```

## Option 3: Hybrid Approach

Use fetchmail's smtphost but keep post-processing:

```conf
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   smtphost localhost/2525
   postconnect "/usr/local/bin/post-classify-log.sh"
   keep
   no fetchall
   no rewrite
   idle
```

Create `post-classify-log.sh`:
```bash
#!/bin/bash
# Log classifier stats after processing
tail -1 /app/data/classifier.db | logger -t email-classifier
```

## Docker Compose Network Configuration

Ensure fetchmail can reach the classifier:

### If Fetchmail is on Host System

Add to your `.env`:
```bash
# Allow host system to reach classifier
CLASSIFIER_HOST=0.0.0.0
CLASSIFIER_PORT=2525
```

Fetchmail config uses:
```conf
smtphost localhost/2525
```

### If Fetchmail is in Docker

Create shared network:
```bash
docker network create mailserver-network
```

Update `docker-compose.yml` for fetchmail:
```yaml
services:
  fetchmail:
    networks:
      - mailserver-network
    # ... other config
```

Fetchmail config uses:
```conf
smtphost email-classifier/2525
```

## Sendmail Path Configuration

The classifier needs to deliver to sendmail. Configure the path:

### For docker-mailserver

Add to `.env`:
```bash
SENDMAIL_PATH=/usr/sbin/sendmail
```

Mount sendmail into classifier:
```yaml
# docker-compose.yml
services:
  email-classifier:
    volumes:
      - /usr/sbin/sendmail:/usr/sbin/sendmail:ro
```

### For Postfix

```bash
SENDMAIL_PATH=/usr/sbin/sendmail
```

### For Other MTAs

Find your sendmail path:
```bash
which sendmail
```

Update `.env` accordingly.

## Complete Docker Setup

### docker-compose.yml (Updated)

```yaml
version: '3.8'

services:
  email-classifier:
    build: .
    container_name: email-classifier
    environment:
      - IMAP_HOST=${IMAP_HOST}
      - IMAP_PORT=${IMAP_PORT}
      - IMAP_USERS=${IMAP_USERS}
      - TRAINING_INTERVAL=${TRAINING_INTERVAL}
      - CONFIDENCE_THRESHOLD=${CONFIDENCE_THRESHOLD}
      - SENDMAIL_PATH=${SENDMAIL_PATH:-/usr/sbin/sendmail}
    volumes:
      - ./data:/app/data
      - ./models:/app/models
      - /usr/sbin/sendmail:/usr/sbin/sendmail:ro  # Mount sendmail
    ports:
      - "8080:8080"
      - "2525:2525"
    restart: unless-stopped
    networks:
      - mailserver-network

networks:
  mailserver-network:
    external: true
```

## Testing the Integration

### 1. Send Test Email

```bash
# From host
echo "Test email body" | mail -s "Test Classification" paul@g
```

### 2. Check Classifier Logs

```bash
docker logs -f email-classifier
```

Expected output:
```
Received email from sender@example.com to ['paul@g']
  Classification: personal (confidence: 0.85, time: 0.123s)
  Subject: Test Classification
  ✓ Delivered to INBOX
```

### 3. Verify Headers

Check the delivered email for classification headers:
```bash
cat /var/mail/paul@g | grep "^X-Email"
```

Should show:
```
X-Email-Category: personal
X-Classification-Confidence: 0.850
X-Classifier-Time: 0.123
```

### 4. Check Dashboard

Visit http://localhost:8080 to see the classification logged.

## Using Classification Headers for Filtering

### Sieve Filters (Dovecot)

```sieve
require ["fileinto"];

# Route to Shopping folder
if header :contains "X-Email-Category" "shopping" {
    fileinto "Shopping";
    stop;
}

# Route to Junk
if header :contains "X-Email-Category" "spam" {
    fileinto "Junk";
    stop;
}
```

### Procmail

```procmail
:0
* ^X-Email-Category: shopping
Shopping

:0
* ^X-Email-Category: spam
Junk
```

### Postfix Header Checks

```conf
# /etc/postfix/header_checks
/^X-Email-Category: shopping/ FILTER smtp:localhost:2526
/^X-Email-Category: spam/ FILTER smtp:localhost:2527
```

## Troubleshooting

### Classifier Not Receiving Emails

**Check connectivity:**
```bash
telnet localhost 2525
```

**Check Docker network:**
```bash
docker network inspect mailserver-network
```

### Sendmail Errors

**Verify sendmail path:**
```bash
docker exec email-classifier ls -l /usr/sbin/sendmail
```

**Check sendmail logs:**
```bash
tail -f /var/log/mail.log
```

### Emails Not Being Classified

**Check classifier logs:**
```bash
docker logs email-classifier | grep "Classification:"
```

**Verify training data:**
```bash
docker exec email-classifier sqlite3 /app/data/classifier.db "SELECT COUNT(*) FROM training_data"
```

Should return > 0. If 0, classifier needs training data.

### Headers Not Being Added

**Verify SMTP conversation:**
```bash
# Send test email manually
telnet localhost 2525
EHLO localhost
MAIL FROM: test@example.com
RCPT TO: paul@g
DATA
Subject: Test
From: test@example.com
To: paul@g

Test body
.
QUIT
```

Check if response includes classification.

## Performance Considerations

### Fetchmail + Classifier Latency

Total time per email:
- Fetchmail download: ~100-500ms
- Classification: ~100-150ms
- Sendmail delivery: ~50-100ms
- **Total: ~250-750ms per email**

This is acceptable for typical email volumes.

### High Volume (1000+ emails/hour)

For high volume:
1. Use `fetchall` initially to process backlog
2. Switch to `idle` for real-time processing
3. Consider multiple classifier instances
4. Monitor classifier performance in dashboard

## Migration Strategy

### Step 1: Test in Parallel

Keep your existing setup running and test classifier separately:

```conf
# Original (keep running)
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   mda "/usr/local/bin/classify-and-log.sh | /usr/sbin/sendmail -i -f %F -- %T"
   keep
   no fetchall
   no rewrite

# Test classifier (different account or folder)
poll imap.gmail.com with proto IMAP folder "Test"
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul+test@g' here
   smtphost localhost/2525
   keep
   no fetchall
```

### Step 2: Monitor Performance

Watch dashboard at http://localhost:8080 for:
- Classification accuracy
- Processing time
- Any errors

### Step 3: Full Cutover

Once satisfied, update main fetchmail config to use classifier.

### Step 4: Archive Old Script

Keep your old `classify-and-log.sh` as backup:
```bash
mv classify-and-log.sh classify-and-log.sh.backup
```

## Support

For issues:
1. Check classifier logs: `docker logs email-classifier`
2. Check dashboard: http://localhost:8080
3. Verify connectivity: `telnet localhost 2525`
4. Review fetchmail logs: `tail -f /var/log/fetchmail.log`
