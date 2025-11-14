# Update: SMTP Relay (No Sendmail Required!)

## What Changed

**Previous approach:** Classifier mounted `/usr/sbin/sendmail` from host  
**New approach:** Classifier forwards via SMTP to docker-mailserver

## Why This Is Better

✅ **No sendmail binary needed** - Works with containerized mail servers  
✅ **Simpler setup** - No volume mounts or binary paths  
✅ **More flexible** - Works with any SMTP server  
✅ **Container-native** - Direct container-to-container communication  
✅ **Docker-mailserver friendly** - Designed for DMS workflows  

## Key Updates

### 1. smtp_server.py
- Uses `smtplib.SMTP` instead of subprocess to sendmail
- Forwards to configurable SMTP server
- Supports TLS and authentication

### 2. config.py
```python
# Old
SENDMAIL_PATH = os.getenv('SENDMAIL_PATH', '/usr/sbin/sendmail')

# New
DELIVERY_HOST = os.getenv('DELIVERY_HOST', 'mailserver')
DELIVERY_PORT = int(os.getenv('DELIVERY_PORT', 25))
DELIVERY_USE_TLS = os.getenv('DELIVERY_USE_TLS', 'false').lower() == 'true'
DELIVERY_USER = os.getenv('DELIVERY_USER', '')
DELIVERY_PASSWORD = os.getenv('DELIVERY_PASSWORD', '')
```

### 3. docker-compose.yml
```yaml
# Old
volumes:
  - /usr/sbin/sendmail:/usr/sbin/sendmail:ro

environment:
  - SENDMAIL_PATH=/usr/sbin/sendmail

# New
environment:
  - DELIVERY_HOST=mailserver
  - DELIVERY_PORT=25
  - DELIVERY_USE_TLS=false

# No sendmail volume needed!
```

### 4. .env
```bash
# Old
SENDMAIL_PATH=/usr/sbin/sendmail

# New
DELIVERY_HOST=mailserver
DELIVERY_PORT=25
DELIVERY_USE_TLS=false
DELIVERY_USER=
DELIVERY_PASSWORD=
```

## How It Works Now

```
┌──────────────┐
│  Fetchmail   │
└──────┬───────┘
       │ SMTP
       ▼
┌──────────────────────────────┐
│  Classifier Container        │
│                              │
│  1. Receive email (port 2525)│
│  2. Classify with DistilBERT │
│  3. Add headers              │
│  4. Forward via SMTP         │
└──────┬───────────────────────┘
       │ SMTP
       ▼
┌──────────────────────────────┐
│  docker-mailserver Container │
│  (port 25)                   │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────┐
│   Mailbox    │
└──────────────┘
```

## Migration Steps

If you already have the old version deployed:

### 1. Update Files
Replace these files with new versions:
- `smtp_server.py`
- `config.py`
- `docker-compose.yml`
- `.env.example`

### 2. Update .env
```bash
# Remove
SENDMAIL_PATH=/usr/sbin/sendmail

# Add
DELIVERY_HOST=mailserver  # Your DMS container name
DELIVERY_PORT=25
```

### 3. Rebuild
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### 4. Verify
```bash
# Check classifier can reach mailserver
docker exec email-classifier telnet mailserver 25

# Send test email
echo "Test" | mail -s "Test" paul@yourdomain.com

# Check logs
docker logs -f email-classifier
```

## Configuration Examples

### Basic (docker-mailserver on same network)
```bash
DELIVERY_HOST=mailserver
DELIVERY_PORT=25
```

### With TLS
```bash
DELIVERY_HOST=mailserver
DELIVERY_PORT=587
DELIVERY_USE_TLS=true
```

### With Authentication
```bash
DELIVERY_HOST=mailserver
DELIVERY_PORT=587
DELIVERY_USE_TLS=true
DELIVERY_USER=paul@yourdomain.com
DELIVERY_PASSWORD=yourpassword
```

### External Mail Server
```bash
DELIVERY_HOST=smtp.gmail.com
DELIVERY_PORT=587
DELIVERY_USE_TLS=true
DELIVERY_USER=youruser@gmail.com
DELIVERY_PASSWORD=yourapppassword
```

## Benefits for Your Setup

Since your sendmail is in docker-mailserver:

✅ **No complexity** - Containers talk directly  
✅ **No volume mounts** - Just network communication  
✅ **Standard SMTP** - Works with any mail server  
✅ **Easy debugging** - Clear SMTP logs on both sides  
✅ **Flexible** - Easy to change mail server later  

## Troubleshooting

### Can't reach mailserver

**Check container name:**
```bash
docker ps --format "table {{.Names}}"
```

**Test connectivity:**
```bash
docker exec email-classifier ping mailserver
docker exec email-classifier telnet mailserver 25
```

**Update DELIVERY_HOST:**
```bash
# In .env
DELIVERY_HOST=your-actual-container-name
```

### Authentication errors

**Enable auth in .env:**
```bash
DELIVERY_USER=youruser
DELIVERY_PASSWORD=yourpass
```

**Or disable auth requirement in docker-mailserver:**
```yaml
# docker-mailserver compose
environment:
  - PERMIT_DOCKER=network
```

### TLS errors

**Try without TLS for container-to-container:**
```bash
DELIVERY_USE_TLS=false
DELIVERY_PORT=25
```

**Or use TLS on port 587:**
```bash
DELIVERY_USE_TLS=true
DELIVERY_PORT=587
```

## Verification

After updating, verify:

```bash
# 1. Classifier starts successfully
docker ps | grep email-classifier

# 2. Can reach mailserver
docker exec email-classifier telnet mailserver 25

# 3. Test email delivery
echo "Test" | mail -s "Test" paul@yourdomain.com

# 4. Check classifier logs
docker logs email-classifier | grep "Delivered to"

# Should show:
# ✓ Delivered to mailserver:25

# 5. Check mailserver received it
docker logs mailserver | grep -i postfix
```

## Documentation

Updated guides:
- **[DOCKER_MAILSERVER.md](DOCKER_MAILSERVER.md)** - Complete DMS integration (NEW!)
- **[FETCHMAIL_UPDATE.md](FETCHMAIL_UPDATE.md)** - Quick setup guide (UPDATED)
- **[README.md](README.md)** - Updated with SMTP relay info

## Summary

**Before:** Classifier → sendmail binary → mailbox  
**After:** Classifier → SMTP → docker-mailserver → mailbox

**Result:** Simpler, more flexible, container-native architecture that works perfectly with docker-mailserver!

No sendmail binary required! 🎉
