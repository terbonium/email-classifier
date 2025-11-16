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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
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
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)

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
                         old_category: str, new_category: str):
    """Log when a user moves an email (reclassification detected)"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO reclassifications
                 (message_id, user_email, subject, old_category, new_category)
                 VALUES (?, ?, ?, ?, ?)''',
              (message_id, user_email, subject, old_category, new_category))
    conn.commit()
    conn.close()
    print(f"📝 Reclassification logged: {old_category} → {new_category} | {subject[:50]}")

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
