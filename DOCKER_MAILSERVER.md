# Docker-Mailserver Integration Guide

This guide shows how to integrate the email classifier with docker-mailserver (DMS) when both run in Docker containers.

## Architecture

```
Fetchmail → Classifier:2525 → docker-mailserver:25 → Mailbox
  (IMAP)      (classify)         (deliver)
               ↓
          Add headers:
          X-Email-Category
          X-Classification-Confidence
```

## Prerequisites

- docker-mailserver running and configured
- Both containers on same Docker network
- Fetchmail configured (can be on host or in container)

## Setup

### 1. Network Configuration

Create a shared Docker network:

```bash
docker network create mailserver-network
```

### 2. Configure docker-mailserver

Your docker-mailserver should already be on this network. If not, add to its `docker-compose.yml`:

```yaml
services:
  mailserver:
    # ... your existing config
    networks:
      - mailserver-network

networks:
  mailserver-network:
    external: true
```

### 3. Configure Email Classifier

Edit `.env`:

```bash
# IMAP settings (for training from your mailbox)
IMAP_HOST=mailserver  # or your DMS hostname
IMAP_PORT=993

# Your email credentials
IMAP_USERS=paul@yourdomain.com:yourpassword

# Delivery settings (forward to docker-mailserver)
DELIVERY_HOST=mailserver  # DMS container name
DELIVERY_PORT=25          # DMS SMTP port
DELIVERY_USE_TLS=false    # Usually false for container-to-container
```

### 4. Find Your DMS Container Name

```bash
docker ps | grep mailserver
```

Common names:
- `mailserver`
- `docker-mailserver`
- `mail`

Update `DELIVERY_HOST` in `.env` to match.

### 5. Start the Classifier

```bash
docker-compose up -d
```

### 6. Configure Fetchmail

**If fetchmail is on the host:**

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

**If fetchmail is in Docker:**

```conf
poll imap.gmail.com with proto IMAP
   user 'prgo' there with password 'pggbuj' ssl
   is 'paul@g' here
   smtphost email-classifier/2525  # Use container name
   keep
   no fetchall
   no rewrite
   idle
```

## Flow Diagram

```
┌──────────────┐
│    Gmail     │ IMAP
│              │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────┐
│  Fetchmail (host or container)           │
│  - Polls Gmail via IMAP                  │
│  - Sends to classifier:2525 via SMTP     │
└──────┬───────────────────────────────────┘
       │ SMTP (port 2525)
       ▼
┌──────────────────────────────────────────┐
│  Email Classifier Container              │
│  ┌────────────────────────────────────┐  │
│  │  1. Receive email                  │  │
│  │  2. Extract text (subject + body)  │  │
│  │  3. DistilBERT classification      │  │
│  │  4. Add headers:                   │  │
│  │     X-Email-Category: shopping     │  │
│  │     X-Classification-Confidence    │  │
│  └────────────────────────────────────┘  │
└──────┬───────────────────────────────────┘
       │ SMTP (port 25)
       ▼
┌──────────────────────────────────────────┐
│  docker-mailserver Container             │
│  ┌────────────────────────────────────┐  │
│  │  1. Receive via SMTP               │  │
│  │  2. Process with Postfix           │  │
│  │  3. Filter with Sieve (optional)   │  │
│  │  4. Deliver to mailbox             │  │
│  └────────────────────────────────────┘  │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   Mailbox    │
│  (IMAP/POP3) │
└──────────────┘
```

## Verification

### 1. Check Networks

Both containers should be on `mailserver-network`:

```bash
docker network inspect mailserver-network
```

Should show both `email-classifier` and your mailserver container.

### 2. Test Connectivity

From classifier to mailserver:

```bash
docker exec email-classifier telnet mailserver 25
```

Should connect successfully.

### 3. Send Test Email

```bash
echo "Test email" | mail -s "Test Classification" paul@yourdomain.com
```

### 4. Watch Classifier Logs

```bash
docker logs -f email-classifier
```

Expected output:
```
Received email from sender@gmail.com to ['paul@yourdomain.com']
  Classification: personal (confidence: 0.85, time: 0.123s)
  Subject: Test Classification
  ✓ Delivered to mailserver:25
```

### 5. Check Email Headers

In your email client, view full headers:

```
X-Email-Category: personal
X-Classification-Confidence: 0.850
X-Classifier-Time: 0.123
```

## Using Classification Headers

### Option 1: Sieve Filters (Recommended)

docker-mailserver supports Sieve. Create `/path/to/mailserver/config/sieve-filter/before.sieve`:

```sieve
require ["fileinto", "mailbox"];

# Shopping emails
if header :contains "X-Email-Category" "shopping" {
    fileinto :create "Shopping";
    stop;
}

# Spam
if header :contains "X-Email-Category" "spam" {
    fileinto :create "Junk";
    stop;
}

# Personal goes to INBOX (default)
```

Restart docker-mailserver:
```bash
docker restart mailserver
```

### Option 2: Postfix Header Checks

Add to docker-mailserver's Postfix config:

```conf
header_checks = regexp:/tmp/docker-mailserver/header_checks
```

Create `header_checks`:
```
/^X-Email-Category: shopping/ FILTER smtp:[127.0.0.1]:10026
/^X-Email-Category: spam/ FILTER smtp:[127.0.0.1]:10027
```

## Complete docker-compose.yml Example

```yaml
version: '3.8'

services:
  mailserver:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    container_name: mailserver
    hostname: mail.yourdomain.com
    ports:
      - "25:25"
      - "143:143"
      - "587:587"
      - "993:993"
    volumes:
      - ./dms/mail-data:/var/mail
      - ./dms/mail-state:/var/mail-state
      - ./dms/mail-logs:/var/log/mail
      - ./dms/config:/tmp/docker-mailserver
      - /etc/localtime:/etc/localtime:ro
    environment:
      - ENABLE_SPAMASSASSIN=1
      - SPAMASSASSIN_SPAM_TO_INBOX=1
      - ENABLE_CLAMAV=1
      - ENABLE_FAIL2BAN=1
      - ENABLE_POSTGREY=1
      - ONE_DIR=1
      - DMS_DEBUG=0
    cap_add:
      - NET_ADMIN
    restart: always
    networks:
      - mailserver-network

  email-classifier:
    build: ./email-classifier
    container_name: email-classifier
    environment:
      - IMAP_HOST=mailserver
      - IMAP_PORT=993
      - IMAP_USERS=paul@yourdomain.com:yourpassword
      - DELIVERY_HOST=mailserver
      - DELIVERY_PORT=25
      - TRAINING_INTERVAL=3600
    volumes:
      - ./email-classifier/data:/app/data
      - ./email-classifier/models:/app/models
    ports:
      - "8080:8080"
      - "2525:2525"
    restart: unless-stopped
    networks:
      - mailserver-network
    depends_on:
      - mailserver

networks:
  mailserver-network:
    driver: bridge
```

## Troubleshooting

### Classifier can't reach mailserver

**Error:** `Connection refused to mailserver:25`

**Solutions:**

1. Check container name:
   ```bash
   docker ps --format "table {{.Names}}\t{{.Networks}}"
   ```

2. Verify network:
   ```bash
   docker network inspect mailserver-network
   ```

3. Test connectivity:
   ```bash
   docker exec email-classifier ping mailserver
   docker exec email-classifier telnet mailserver 25
   ```

4. Update `DELIVERY_HOST` in `.env` to match actual container name

### Emails not being delivered

**Check classifier logs:**
```bash
docker logs email-classifier | grep -A5 "Delivery error"
```

**Check mailserver logs:**
```bash
docker logs mailserver | grep -i postfix
```

**Common issues:**

1. **Port 25 not open in mailserver:**
   - Verify `ports: - "25:25"` in mailserver compose
   - Check firewall rules

2. **Authentication required:**
   - Add to `.env`:
     ```bash
     DELIVERY_USER=yourusername
     DELIVERY_PASSWORD=yourpassword
     ```

3. **TLS required:**
   - Add to `.env`:
     ```bash
     DELIVERY_USE_TLS=true
     DELIVERY_PORT=587
     ```

### Headers not appearing

**Verify classifier is adding headers:**
```bash
docker logs email-classifier | grep "X-Email-Category"
```

**Check raw email:**
```bash
# In your mail client, view source/raw message
# Look for X-Email-Category header
```

**If missing:**
- Classifier may not be in the path
- Check fetchmail is routing through classifier
- Verify: `smtphost localhost/2525` in fetchmail config

### Training not working

**Check IMAP connection:**
```bash
docker logs email-classifier | grep -i "training\|imap"
```

**Common issues:**

1. **Wrong credentials:**
   - Update `IMAP_USERS` in `.env`
   - Format: `email:password`

2. **IMAP not enabled in docker-mailserver:**
   - Add to mailserver environment:
     ```yaml
     - ENABLE_IMAP=1
     ```

3. **Folders don't exist:**
   - Create folders in your email client:
     - INBOX (should exist)
     - Shopping
     - Junk

### Performance Issues

**Slow classification (>1s per email):**

1. Check resources:
   ```bash
   docker stats email-classifier
   ```

2. Increase memory if needed:
   ```yaml
   services:
     email-classifier:
       deploy:
         resources:
           limits:
             memory: 3G
   ```

3. Check CPU usage - classification is CPU-intensive

## Advanced: LMTP Delivery

For even better integration, use LMTP instead of SMTP:

### Update smtp_server.py

Replace SMTP delivery with LMTP:
```python
from smtplib import LMTP

lmtp = LMTP(config.DELIVERY_HOST, config.DELIVERY_PORT)
lmtp.sendmail(envelope.mail_from, envelope.rcpt_tos, modified_email.encode('utf-8'))
lmtp.quit()
```

### Configure docker-mailserver for LMTP

Enable LMTP in docker-mailserver:
```yaml
environment:
  - ENABLE_LMTP=1
```

### Update .env
```bash
DELIVERY_PORT=24  # LMTP port
```

## Monitoring

### Dashboard

Access the web dashboard:
```
http://localhost:8080
```

Shows:
- Total emails processed
- Category distribution
- Average processing time
- Recent classifications
- Training data stats

### Logs

**Classifier logs:**
```bash
docker logs -f email-classifier
```

**Mailserver logs:**
```bash
docker logs -f mailserver
```

**Combined view:**
```bash
docker logs -f email-classifier mailserver
```

### Database Queries

**Classification stats:**
```bash
docker exec email-classifier sqlite3 /app/data/classifier.db \
  "SELECT predicted_category, COUNT(*) as count FROM classifications GROUP BY predicted_category"
```

**Recent classifications:**
```bash
docker exec email-classifier sqlite3 /app/data/classifier.db \
  "SELECT timestamp, subject, predicted_category, confidence FROM classifications ORDER BY timestamp DESC LIMIT 10"
```

## Best Practices

1. **Use separate network:** Keep mail services isolated
2. **Monitor logs:** Watch for delivery errors
3. **Regular backups:** Backup `/app/data` and `/app/models`
4. **Test before production:** Use test account first
5. **Set up alerts:** Monitor classifier container health
6. **Keep training data:** Don't delete old emails until model is trained

## Security Considerations

1. **Network isolation:** Use dedicated Docker network
2. **No public ports:** Only expose 8080 for dashboard if needed
3. **Secure credentials:** Use Docker secrets for passwords
4. **TLS for delivery:** Use `DELIVERY_USE_TLS=true` if possible
5. **Monitor access:** Check dashboard access logs
6. **Regular updates:** Keep classifier and DMS updated

## Support

- Dashboard: http://localhost:8080
- Classifier logs: `docker logs email-classifier`
- DMS logs: `docker logs mailserver`
- Network status: `docker network inspect mailserver-network`
