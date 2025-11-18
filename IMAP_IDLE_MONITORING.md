# IMAP IDLE Real-Time Monitoring

This document describes the IMAP IDLE real-time monitoring feature for detecting email reclassifications.

## Overview

The email classifier now supports **real-time reclassification detection** using IMAP IDLE (RFC 2177). When users move emails between folders (INBOX, Shopping, Junk), the system immediately detects these changes and updates the training data, improving the model's accuracy through continuous learning.

## How It Works

### Three Detection Methods

The system uses a **hybrid approach** with three complementary detection methods:

1. **Real-Time IDLE Monitoring** (NEW) ⚡
   - Continuously monitors INBOX, Shopping, and Junk folders
   - Uses IMAP IDLE protocol for immediate change notifications
   - Triggers reclassification check within seconds of email movements
   - Runs in separate threads per folder for parallel monitoring

2. **Nightly Scheduled Check** 📅
   - Runs daily at configured time (default: 3:00 AM)
   - Performs comprehensive reclassification scan before model retraining
   - Ensures no changes are missed due to IDLE connection issues
   - Automatic model retraining with updated training data

3. **Manual Trigger** 🔘
   - "Check for Reclassified Emails" button in web dashboard
   - Allows immediate on-demand checking
   - Useful for testing or immediate feedback

### Architecture

```
┌─────────────────────────────────────────────────┐
│           IMAP IDLE Monitor Manager             │
│  ┌──────────────┬──────────────┬──────────────┐ │
│  │   INBOX      │   Shopping   │     Junk     │ │
│  │   Thread     │    Thread    │    Thread    │ │
│  │   (IDLE)     │    (IDLE)    │    (IDLE)    │ │
│  └──────┬───────┴──────┬───────┴──────┬───────┘ │
│         │              │              │          │
│         └──────────────┴──────────────┘          │
│                     │                            │
└─────────────────────┼────────────────────────────┘
                      │
              ┌───────▼────────┐
              │  on_idle_change │
              │   Callback      │
              └───────┬─────────┘
                      │
         ┌────────────▼───────────┐
         │ check_reclassifications│
         │  (Thread-Safe)         │
         └────────────┬───────────┘
                      │
              ┌───────▼────────┐
              │ Update Training │
              │      Data       │
              └─────────────────┘
```

## Configuration

All IDLE monitoring settings can be configured via environment variables:

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IDLE_ENABLED` | `true` | Enable/disable IMAP IDLE monitoring |
| `IDLE_TIMEOUT` | `1740` (29 min) | IDLE timeout in seconds (max 29 min per RFC 2177) |
| `IDLE_RATE_LIMIT` | `30` | Minimum seconds between reclassification checks per folder |
| `TRAINING_SCHEDULE` | `3:00` | Daily time for scheduled check and retrain (HH:MM format) |

### Example Configuration

```bash
# Enable IDLE monitoring (default)
IDLE_ENABLED=true

# Use shorter IDLE timeout (10 minutes)
IDLE_TIMEOUT=600

# Allow checks every minute per folder
IDLE_RATE_LIMIT=60

# Schedule nightly retrain at 2:00 AM
TRAINING_SCHEDULE=2:00
```

### Disabling IDLE

To disable real-time IDLE monitoring and use only scheduled checks:

```bash
IDLE_ENABLED=false
```

## Technical Details

### IMAP IDLE Protocol

- **RFC 2177 Compliance**: Maximum 29-minute IDLE timeout
- **Automatic Renewal**: IDLE connections are automatically renewed before timeout
- **Multi-Folder Support**: Each folder monitored in a separate thread
- **Change Detection**: Responds to:
  - New messages (EXISTS)
  - Deleted messages (EXPUNGE)
  - Flag changes (FETCH)

### Thread Safety

- **Reclassification Lock**: Prevents concurrent reclassification checks
- **Rate Limiting**: Prevents excessive checking during rapid changes
- **Connection Management**: Each folder has its own IMAP connection

### Error Handling

- **Exponential Backoff**: Reconnection delays: 1s → 2s → 4s → 8s → ... → 5min max
- **Graceful Degradation**: Falls back to scheduled checks if IDLE fails
- **Connection Recovery**: Automatic reconnection on network errors
- **Clean Shutdown**: Proper cleanup on KeyboardInterrupt

## Benefits

### For Users

- **Immediate Feedback**: Reclassifications detected within seconds
- **Better Learning**: Model adapts faster to user preferences
- **Lower Latency**: No waiting for hourly/daily scheduled checks
- **Transparent**: Console logs show real-time detection

### For System

- **Reduced Polling**: No need for frequent IMAP scans
- **Lower Server Load**: IDLE is more efficient than polling
- **Scalable**: Handles multiple users and folders efficiently
- **Reliable**: Hybrid approach ensures no missed changes

## Monitoring and Logs

### Console Output

When IDLE detects changes, you'll see output like:

```
🔔 IDLE detected changes in Shopping for user@example.com
   Triggering real-time reclassification check...
Checking for reclassifications by user@example.com...
  📊 Tracking 450 emails in training database
  🔍 Scanning IMAP folders for emails since 2025-10-18...

  🔄 MESSAGE RECLASSIFICATION DETECTED
     Message-ID: <abc123@mail.example.com>
     Subject: Your Amazon Order Confirmation
     Original Category: personal (folder: INBOX)
     New Category: shopping (folder: Shopping)
     User: user@example.com
     Action: Message moved from 'INBOX' to 'Shopping'

   ✅ Real-time check found 1 reclassifications
   📝 Model will be retrained at next scheduled time
```

### Startup Messages

```
=== Starting Real-Time IMAP IDLE Monitoring ===
Started IDLE thread for folder: INBOX
Started IDLE thread for folder: Shopping
Started IDLE thread for folder: Junk
✅ IDLE monitoring started for real-time reclassification detection
   Changes to INBOX, Shopping, and Junk folders will trigger immediate checks
   IDLE timeout: 1740s, Rate limit: 30s
```

### Shutdown Messages

```
=== Shutting down training loop ===
Stopping IDLE monitor...
[INBOX] IDLE monitor thread stopped for user@example.com
[Shopping] IDLE monitor thread stopped for user@example.com
[Junk] IDLE monitor thread stopped for user@example.com
Shutdown complete
```

## Web Dashboard

The web dashboard shows:

- **Real-time reclassifications** in the "Recent Reclassifications" table
- **Manual trigger button**: "Check for Reclassified Emails"
- **Auto-refresh**: Dashboard updates every 30 seconds (10s during training)
- **Reclassification count** in statistics

## Workflow

### User Moves Email

1. User receives email classified as "personal" in INBOX
2. User realizes it's shopping-related and moves it to Shopping folder
3. **IDLE immediately detects** the folder change
4. System triggers reclassification check (with rate limiting)
5. Change logged to database and console
6. Next scheduled retrain incorporates the correction
7. Future similar emails classified correctly

### Nightly Retrain

1. At configured time (default 3:00 AM):
   - Run comprehensive reclassification check
   - Log any new reclassifications
   - Retrain model with updated training data
2. Model ready with improved accuracy for next day

## Performance Considerations

### Network

- IDLE maintains persistent connections (3 per user: INBOX, Shopping, Junk)
- Minimal bandwidth usage (only notifications, not full email content)
- Automatic reconnection on network issues

### CPU

- Reclassification checks scan only last 30 days of emails
- Header-only fetching (much faster than full email bodies)
- Rate limiting prevents excessive checking

### Memory

- Each IDLE thread uses minimal memory (~1-2 MB)
- Connection pooling for efficient resource usage

## Troubleshooting

### IDLE Not Starting

Check logs for error messages:
```
⚠️  Failed to start IDLE monitoring: [error message]
   Falling back to scheduled checks only
```

Common causes:
- IMAP server doesn't support IDLE
- Network connectivity issues
- Authentication failures

Solution: Set `IDLE_ENABLED=false` to use scheduled checks only

### Too Many Checks

If you see frequent rate-limiting messages:
```
⏭️  Skipping IDLE check for user@example.com/INBOX (checked 15s ago)
```

Solution: Increase `IDLE_RATE_LIMIT` (e.g., to 60 seconds)

### Connection Drops

IDLE automatically reconnects with exponential backoff:
```
[INBOX] Error in IDLE monitor for user@example.com: connection reset
[INBOX] Reconnecting in 2 seconds...
```

This is normal for long-running connections. The system will recover automatically.

## Migration from Polling

If you were previously using only scheduled checks:

1. **No changes needed** - IDLE monitoring is enabled by default
2. **Existing behavior preserved** - Scheduled checks still run
3. **Backwards compatible** - Manual trigger button still works
4. **Incremental improvement** - IDLE adds real-time detection on top

## Code Structure

### New Files

- `imap_idle_monitor.py` - IDLE monitoring implementation
  - `IMAPIdleMonitor` - Per-user IDLE monitor
  - `IMAPIdleMonitorManager` - Multi-user manager

### Modified Files

- `trainer.py` - Integrated IDLE monitoring
  - `on_idle_change()` - IDLE callback handler
  - `training_loop()` - Starts IDLE monitor
  - `check_reclassifications()` - Thread-safe (unchanged logic)

- `config.py` - Added IDLE configuration
  - `IDLE_ENABLED`
  - `IDLE_TIMEOUT`
  - `IDLE_RATE_LIMIT`

### Unchanged

- `web_ui.py` - Manual trigger button works as before
- `smtp_server.py` - Classification logic unchanged
- `classifier.py` - Model training unchanged

## Future Enhancements

Potential improvements for future versions:

- **IDLE status API endpoint** - Show IDLE connection status in web UI
- **Per-user IDLE settings** - Different timeouts per user
- **Immediate retraining option** - Retrain on every N reclassifications
- **IDLE statistics** - Track IDLE uptime, reconnections, changes detected
- **Email notifications** - Alert on reclassifications via email
- **Webhook support** - Trigger external systems on reclassifications

## References

- [RFC 2177 - IMAP4 IDLE command](https://tools.ietf.org/html/rfc2177)
- [imapclient Documentation](https://imapclient.readthedocs.io/)
- [IMAP IDLE Best Practices](https://tools.ietf.org/html/rfc2177#section-3)
