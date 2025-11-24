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

# IMAP IDLE Configuration
IDLE_ENABLED = os.getenv('IDLE_ENABLED', 'true').lower() == 'true'
IDLE_TIMEOUT = int(os.getenv('IDLE_TIMEOUT', 29 * 60))  # Default 29 minutes (RFC 2177 max)
IDLE_RATE_LIMIT = int(os.getenv('IDLE_RATE_LIMIT', 30))  # Min seconds between checks per folder

# SMTP Delivery settings (for forwarding classified emails)
DELIVERY_HOST = os.getenv('DELIVERY_HOST', 'mailserver')
DELIVERY_PORT = int(os.getenv('DELIVERY_PORT', 25))
DELIVERY_USE_TLS = os.getenv('DELIVERY_USE_TLS', 'false').lower() == 'true'
DELIVERY_USER = os.getenv('DELIVERY_USER', '')
DELIVERY_PASSWORD = os.getenv('DELIVERY_PASSWORD', '')

# Footer settings (for adding classifier links to emails)
FOOTER_ENABLED = os.getenv('FOOTER_ENABLED', 'true').lower() == 'true'
CLASSIFIER_UI_BASE_URL = os.getenv('CLASSIFIER_UI_BASE_URL', 'http://localhost:8080')

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
                  personal_prob REAL,
                  shopping_prob REAL,
                  spam_prob REAL,
                  sender_domain TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Migrate existing classifications table - add probability columns if they don't exist
    try:
        c.execute("SELECT personal_prob FROM classifications LIMIT 1")
    except sqlite3.OperationalError:
        # Columns don't exist, add them
        print("Migrating classifications table to add probability columns...")
        c.execute("ALTER TABLE classifications ADD COLUMN personal_prob REAL")
        c.execute("ALTER TABLE classifications ADD COLUMN shopping_prob REAL")
        c.execute("ALTER TABLE classifications ADD COLUMN spam_prob REAL")
        c.execute("ALTER TABLE classifications ADD COLUMN sender_domain TEXT")
        print("Migration complete")

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

    # Model stats table - tracks training metadata
    c.execute('''CREATE TABLE IF NOT EXISTS model_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  model_name TEXT,
                  training_time_seconds REAL,
                  feature_extraction_time_seconds REAL,
                  num_training_samples INTEGER,
                  num_features INTEGER,
                  num_classes INTEGER,
                  num_coefficients INTEGER,
                  model_size_bytes INTEGER,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Training status table - tracks ongoing training
    c.execute('''CREATE TABLE IF NOT EXISTS training_status
                 (id INTEGER PRIMARY KEY CHECK (id = 1),
                  is_training INTEGER DEFAULT 0,
                  started_at DATETIME,
                  num_samples INTEGER,
                  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Initialize with default row
    c.execute('''INSERT OR IGNORE INTO training_status (id, is_training) VALUES (1, 0)''')

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
                       predicted: str, confidence: float, processing_time: float,
                       probabilities: dict = None, sender_domain: str = None):
    """Log a classification decision with full probability breakdown.
    Returns the classification ID for use in footer links."""
    conn = get_db()
    c = conn.cursor()

    # Extract individual probabilities
    personal_prob = probabilities.get('personal') if probabilities else None
    shopping_prob = probabilities.get('shopping') if probabilities else None
    spam_prob = probabilities.get('spam') if probabilities else None

    c.execute('''INSERT INTO classifications
                 (message_id, user_email, subject, predicted_category, confidence, processing_time,
                  personal_prob, shopping_prob, spam_prob, sender_domain)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (message_id, user_email, subject, predicted, confidence, processing_time,
               personal_prob, shopping_prob, spam_prob, sender_domain))

    classification_id = c.lastrowid
    conn.commit()
    conn.close()

    return classification_id

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

def log_model_stats(model_name: str, training_time: float, feature_time: float,
                    num_samples: int, num_features: int, num_classes: int,
                    num_coefficients: int, model_size: int):
    """Log model training statistics"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO model_stats
                 (model_name, training_time_seconds, feature_extraction_time_seconds,
                  num_training_samples, num_features, num_classes, num_coefficients, model_size_bytes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (model_name, training_time, feature_time, num_samples, num_features,
               num_classes, num_coefficients, model_size))
    conn.commit()
    conn.close()

def get_latest_model_stats():
    """Get the latest model statistics"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT model_name, training_time_seconds, feature_extraction_time_seconds,
                        num_training_samples, num_features, num_classes, num_coefficients,
                        model_size_bytes, timestamp
                 FROM model_stats
                 ORDER BY timestamp DESC
                 LIMIT 1''')
    row = c.fetchone()
    conn.close()

    if row:
        return {
            'model_name': row[0],
            'training_time': row[1],
            'feature_time': row[2],
            'num_samples': row[3],
            'num_features': row[4],
            'num_classes': row[5],
            'num_coefficients': row[6],
            'model_size': row[7],
            'last_trained': row[8]
        }
    return None

def set_training_status(is_training: bool, num_samples: int = None):
    """Set the training status"""
    conn = get_db()
    c = conn.cursor()
    if is_training:
        c.execute('''UPDATE training_status
                     SET is_training = 1,
                         started_at = CURRENT_TIMESTAMP,
                         num_samples = ?,
                         updated_at = CURRENT_TIMESTAMP
                     WHERE id = 1''', (num_samples,))
    else:
        c.execute('''UPDATE training_status
                     SET is_training = 0,
                         updated_at = CURRENT_TIMESTAMP
                     WHERE id = 1''')
    conn.commit()
    conn.close()

def get_training_status():
    """Get the current training status"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT is_training, started_at, num_samples, updated_at
                 FROM training_status
                 WHERE id = 1''')
    row = c.fetchone()
    conn.close()

    if row:
        return {
            'is_training': bool(row[0]),
            'started_at': row[1],
            'num_samples': row[2],
            'updated_at': row[3]
        }
    return {'is_training': False, 'started_at': None, 'num_samples': None, 'updated_at': None}
