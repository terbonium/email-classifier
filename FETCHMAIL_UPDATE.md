# Quick Reference: Update Your Fetchmail Config

## Your Current Config
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

---

## ✅ Updated Config (No sendmail needed!)

### New Fetchmail Config
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

### What Changed
- ❌ Removed: `mda "/usr/local/bin/classify-and-log.sh | /usr/sbin/sendmail -i -f %F -- %T"`
- ✅ Added: `smtphost localhost/2525`
- ✅ No sendmail binary required!

### Flow
```
Gmail → Fetchmail → Classifier:2525 → docker-mailserver:25 → Mailbox
                         ↓
                   Adds headers:
                   X-Email-Category: shopping
                   X-Classification-Confidence: 0.85
```

### Setup Steps

1. **Configure environment**
   ```bash
   cd email-classifier
   cp .env.example .env
   ```

   Edit `.env`:
   ```bash
   # IMAP for training
   IMAP_HOST=mailserver
   IMAP_PORT=993
   IMAP_USERS=prgo@gmail.com:pggbuj
   
   # SMTP delivery to docker-mailserver
   DELIVERY_HOST=mailserver  # Your DMS container name
   DELIVERY_PORT=25
   DELIVERY_USE_TLS=false
   ```

2. **Find your mailserver container name**
   ```bash
   docker ps | grep mail
   ```
   
   Update `DELIVERY_HOST` to match (common names: `mailserver`, `docker-mailserver`, `mail`)

3. **Ensure shared network**
   ```bash
   docker network create mailserver-network
   ```

4. **Start classifier**
   ```bash
   ./build.sh
   docker-compose up -d
   ```

5. **Verify connectivity**
   ```bash
   # Classifier should reach your mailserver
   docker exec email-classifier telnet mailserver 25
   ```

6. **Update fetchmail config** (shown above)

7. **Restart fetchmail**
   ```bash
   sudo systemctl restart fetchmail
   # or: killall -HUP fetchmail
   ```

8. **Test**
   ```bash
   # Send test email
   echo "Test" | mail -s "Test Classification" paul@g
   
   # Watch logs
   docker logs -f email-classifier
   ```

---

## Environment Configuration

### Minimal .env
```bash
# IMAP (for training from existing emails)
IMAP_HOST=mailserver
IMAP_PORT=993
IMAP_USERS=paul@yourdomain.com:yourpassword

# Delivery (forward to docker-mailserver)
DELIVERY_HOST=mailserver
DELIVERY_PORT=25
```

### With Authentication (if your mailserver requires it)
```bash
# ... IMAP settings above ...

# Delivery with auth
DELIVERY_HOST=mailserver
DELIVERY_PORT=587
DELIVERY_USE_TLS=true
DELIVERY_USER=paul@yourdomain.com
DELIVERY_PASSWORD=yourpassword
```

---

## Quick Troubleshooting

### "Connection refused" to classifier
```bash
# Check classifier is running
docker ps | grep email-classifier

# Test port
telnet localhost 2525
```

### "Connection refused" to mailserver
```bash
# Check mailserver name
docker ps --format "table {{.Names}}"

# Test from classifier
docker exec email-classifier telnet mailserver 25

# Update DELIVERY_HOST in .env if needed
```

### Emails not being delivered
```bash
# Check classifier logs
docker logs email-classifier | grep -i "delivery\|error"

# Check mailserver logs  
docker logs mailserver | tail -50

# Verify both containers on same network
docker network inspect mailserver-network
```

### No classification happening
```bash
# Check fetchmail is sending to classifier
sudo tail -f /var/log/fetchmail.log

# Should show: "forwarding to localhost/2525"

# Check classifier received it
docker logs -f email-classifier
```

---

## Verification Checklist

✅ Both containers on `mailserver-network`
✅ Classifier can reach mailserver: `docker exec email-classifier telnet mailserver 25`
✅ Fetchmail routes to classifier: `smtphost localhost/2525`  
✅ Classifier logs show delivery: `✓ Delivered to mailserver:25`
✅ Email has headers: `X-Email-Category: personal`
✅ Dashboard shows stats: http://localhost:8080

---

## Complete Example

### docker-compose.yml
```yaml
version: '3.8'

services:
  email-classifier:
    build: .
    container_name: email-classifier
    environment:
      - IMAP_HOST=mailserver
      - IMAP_PORT=993
      - IMAP_USERS=paul@example.com:password
      - DELIVERY_HOST=mailserver
      - DELIVERY_PORT=25
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    ports:
      - "8080:8080"
      - "2525:2525"
    networks:
      - mailserver-network

networks:
  mailserver-network:
    external: true
```

### fetchmailrc
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

That's it! No sendmail binary needed. The classifier receives via SMTP, classifies, and forwards to docker-mailserver via SMTP.

---

## Full Documentation

- **[DOCKER_MAILSERVER.md](DOCKER_MAILSERVER.md)** - Complete DMS integration guide  
- **[README.md](README.md)** - Full system documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Setup guide

---

## Support

### Dashboard
http://localhost:8080

### Check Container Connectivity
```bash
docker network inspect mailserver-network
```

### View Logs
```bash
docker logs -f email-classifier
docker logs -f mailserver
```

### Database Stats
```bash
docker exec email-classifier sqlite3 /app/data/classifier.db \
  "SELECT predicted_category, COUNT(*) FROM classifications GROUP BY predicted_category"
```
