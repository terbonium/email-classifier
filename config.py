import os
import sqlite3
from datetime import datetime
from typing import List, Tuple

# Configuration
IMAP_HOST = os.getenv('IMAP_HOST', 'mail.example.com')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
TRAINING_INTERVAL = int(os.getenv('TRAINING_INTERVAL', 3600))
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', 0.7))
MAX_TRAINING_EMAILS = int(os.getenv('MAX_TRAINING_EMAILS', 500))
MAX_TOTAL_TRAINING_MESSAGES = int(os.getenv('MAX_TOTAL_TRAINING_MESSAGES', 10000))
MAX_TRAINING_TIME_SECONDS = int(os.getenv('MAX_TRAINING_TIME_SECONDS', 300))
TRAINING_SCHEDULE = os.getenv('TRAINING_SCHEDULE', '3:00')

# SMTP Delivery settings (for forwarding classified emails)
DELIVERY_HOST = os.getenv('DELIVERY_HOST', 'mailserver')
DELIVERY_PORT = int(os.getenv('DELIVERY_PORT', 25))
DELIVERY_USE_TLS = os.getenv('DELIVERY_USE_TLS', 'false').lower() == 'true'
DELIVERY_USER = os.getenv('DELIVERY_USER', '')
DELIVERY_PASSWORD = os.getenv('DELIVERY_PASSWORD', '')

# Parse IMAP users from env (format: user1@example.com:password1,user2@example.com:password2)
IMAP_USERS = []
users_str = os.getenv('IMAP_USERS', '')
if users_str:
    for user_pass in users_str.split(','):
        if ':' in user_pass:
            email, password = user_pass.split(':', 1)
            IMAP_USERS.append((email.strip(), password.strip()))

# Directories
DATA_DIR = '/app/data'
MODEL_DIR = '/app/models'
DB_PATH = f'{DATA_DIR}/classifier.db'

# Categories
CATEGORIES = ['personal', 'shopping', 'spam']
FOLDER_MAP = {
    'personal': 'INBOX',
    'shopping': 'Shopping',
    'spam': 'Junk'
}

def init_db():
    """Initialize SQLite database for tracking classifications and stats"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    c = conn.cursor()

    # Enable WAL mode for better concurrent access
    c.execute('PRAGMA journal_mode=WAL')

    # Classifications table
    c.execute('''CREATE TABLE IF NOT EXISTS classifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_id TEXT,
                  user_email TEXT,
                  subject TEXT,
                  predicted_category TEXT,
                  confidence REAL,
                  actual_category TEXT,
                  processing_time REAL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Training data table
    c.execute('''CREATE TABLE IF NOT EXISTS training_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_id TEXT UNIQUE,
                  user_email TEXT,
                  subject TEXT,
                  body TEXT,
                  category TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # User preferences table
    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                 (user_email TEXT PRIMARY KEY,
                  personal_weight REAL DEFAULT 1.0,
                  shopping_weight REAL DEFAULT 1.0,
                  spam_weight REAL DEFAULT 1.0)''')

    # Reclassifications table - tracks when users move emails
    c.execute('''CREATE TABLE IF NOT EXISTS reclassifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_id TEXT,
                  user_email TEXT,
                  subject TEXT,
                  old_category TEXT,
                  new_category TEXT,
                  old_folder TEXT,
                  new_folder TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Migrate existing tables - add folder columns if they don't exist
    try:
        c.execute("SELECT old_folder FROM reclassifications LIMIT 1")
    except sqlite3.OperationalError:
        # Columns don't exist, add them
        print("Migrating reclassifications table to add folder columns...")
        c.execute("ALTER TABLE reclassifications ADD COLUMN old_folder TEXT")
        c.execute("ALTER TABLE reclassifications ADD COLUMN new_folder TEXT")
        print("Migration complete")

    conn.commit()
    conn.close()

def get_db():
    """Get database connection with timeout for better concurrency handling"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # Enable WAL mode for better concurrent access
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def get_existing_classification(message_id: str, user_email: str = None):
    """Check if a message has already been classified and return the result"""
    if not message_id:
        return None

    conn = get_db()
    c = conn.cursor()

    # Query for existing classification, optionally filtered by user
    if user_email:
        c.execute('''SELECT predicted_category, confidence, processing_time, subject
                     FROM classifications
                     WHERE message_id = ? AND user_email = ?
                     ORDER BY timestamp DESC LIMIT 1''',
                  (message_id, user_email))
    else:
        c.execute('''SELECT predicted_category, confidence, processing_time, subject
                     FROM classifications
                     WHERE message_id = ?
                     ORDER BY timestamp DESC LIMIT 1''',
                  (message_id,))

    row = c.fetchone()
    conn.close()

    if row:
        return {
            'category': row[0],
            'confidence': row[1],
            'processing_time': row[2],
            'subject': row[3]
        }
    return None

def log_classification(message_id: str, user_email: str, subject: str,
                       predicted: str, confidence: float, processing_time: float):
    """Log a classification decision"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO classifications
                 (message_id, user_email, subject, predicted_category, confidence, processing_time)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (message_id, user_email, subject, predicted, confidence, processing_time))
    conn.commit()
    conn.close()

def log_reclassification(message_id: str, user_email: str, subject: str,
                         old_category: str, new_category: str,
                         old_folder: str = None, new_folder: str = None):
    """Log when a user moves an email (reclassification detected)"""
    # Default to category names if folders not provided
    if old_folder is None:
        old_folder = FOLDER_MAP.get(old_category, old_category)
    if new_folder is None:
        new_folder = FOLDER_MAP.get(new_category, new_category)

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO reclassifications
                 (message_id, user_email, subject, old_category, new_category, old_folder, new_folder)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (message_id, user_email, subject, old_category, new_category, old_folder, new_folder))
    conn.commit()
    conn.close()

    # Verbose logging
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"📝 RECLASSIFICATION LOGGED [{timestamp}]")
    print(f"   Message-ID: {message_id}")
    print(f"   User: {user_email}")
    print(f"   Subject: {subject}")
    print(f"   Classification Change: {old_category} → {new_category}")
    print(f"   IMAP Folder Move: '{old_folder}' → '{new_folder}'")

def add_to_training_data(message_id: str, user_email: str, subject: str, body: str, category: str):
    """Add a newly classified message to training data for reclassification tracking"""
    conn = get_db()
    c = conn.cursor()

    # Insert or replace the message in training data
    c.execute('''INSERT OR REPLACE INTO training_data
                 (message_id, user_email, subject, body, category)
                 VALUES (?, ?, ?, ?, ?)''',
              (message_id, user_email, subject, body, category))

    conn.commit()

    # Check if we need to cleanup old messages to stay under the limit
    c.execute('SELECT COUNT(*) FROM training_data')
    total_count = c.fetchone()[0]

    if total_count > MAX_TOTAL_TRAINING_MESSAGES:
        # Delete oldest messages beyond the limit
        excess = total_count - MAX_TOTAL_TRAINING_MESSAGES
        c.execute('''DELETE FROM training_data
                     WHERE id IN (
                         SELECT id FROM training_data
                         ORDER BY timestamp ASC
                         LIMIT ?
                     )''', (excess,))
        conn.commit()
        print(f"  🧹 Cleaned up {excess} old training messages (limit: {MAX_TOTAL_TRAINING_MESSAGES})")

    conn.close()

def get_user_weights(user_email: str) -> dict:
    """Get user's category weights"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT personal_weight, shopping_weight, spam_weight FROM user_preferences WHERE user_email = ?',
              (user_email,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {'personal': row[0], 'shopping': row[1], 'spam': row[2]}
    return {'personal': 1.0, 'shopping': 1.0, 'spam': 1.0}

def update_user_weights(user_email: str, weights: dict):
    """Update user's category weights"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_preferences 
                 (user_email, personal_weight, shopping_weight, spam_weight)
                 VALUES (?, ?, ?, ?)''',
              (user_email, weights.get('personal', 1.0), 
               weights.get('shopping', 1.0), weights.get('spam', 1.0)))
    conn.commit()
    conn.close()
