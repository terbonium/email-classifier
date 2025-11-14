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

    # Folder mappings table - dynamically tracks discovered IMAP folders
    c.execute('''CREATE TABLE IF NOT EXISTS folder_mappings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_email TEXT,
                  folder_name TEXT,
                  category TEXT,
                  auto_discovered BOOLEAN DEFAULT 0,
                  message_count INTEGER DEFAULT 0,
                  last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(user_email, folder_name))''')

    # Initialize default folder mappings if they don't exist
    default_mappings = [
        ('personal', 'INBOX', 0),
        ('shopping', 'Shopping', 0),
        ('spam', 'Junk', 0)
    ]

    for category, folder, auto in default_mappings:
        for user_email, _ in IMAP_USERS:
            c.execute('''INSERT OR IGNORE INTO folder_mappings
                        (user_email, folder_name, category, auto_discovered)
                        VALUES (?, ?, ?, ?)''',
                     (user_email, folder, category, auto))

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

def get_folder_mappings(user_email: str = None) -> dict:
    """Get folder to category mappings for a user or all users

    Args:
        user_email: If specified, get mappings for this user only

    Returns:
        dict: {category: folder_name} for single user, or {user_email: {category: folder_name}} for all
    """
    conn = get_db()
    c = conn.cursor()

    if user_email:
        c.execute('''SELECT category, folder_name FROM folder_mappings
                    WHERE user_email = ?
                    ORDER BY category''', (user_email,))
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    else:
        c.execute('''SELECT user_email, category, folder_name FROM folder_mappings
                    ORDER BY user_email, category''')
        rows = c.fetchall()
        conn.close()

        result = {}
        for user, category, folder in rows:
            if user not in result:
                result[user] = {}
            result[user][category] = folder
        return result

def get_all_categories(user_email: str = None) -> List[str]:
    """Get all known categories for a user or across all users

    Args:
        user_email: If specified, get categories for this user only

    Returns:
        List of category names
    """
    conn = get_db()
    c = conn.cursor()

    if user_email:
        c.execute('''SELECT DISTINCT category FROM folder_mappings
                    WHERE user_email = ?
                    ORDER BY category''', (user_email,))
    else:
        c.execute('''SELECT DISTINCT category FROM folder_mappings
                    ORDER BY category''')

    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_folder_mapping(user_email: str, folder_name: str, category: str = None,
                       auto_discovered: bool = True, message_count: int = 0):
    """Add or update a folder mapping

    Args:
        user_email: Email address of the user
        folder_name: IMAP folder name
        category: Category label (defaults to folder name if not specified)
        auto_discovered: Whether this was auto-discovered (vs. default/manual)
        message_count: Number of messages in the folder
    """
    if category is None:
        # Use folder name as category, convert to lowercase and remove special chars
        category = folder_name.lower().replace('/', '_').replace(' ', '_')

    conn = get_db()
    c = conn.cursor()

    # Check if mapping already exists
    c.execute('''SELECT id FROM folder_mappings
                WHERE user_email = ? AND folder_name = ?''',
             (user_email, folder_name))

    if c.fetchone():
        # Update existing mapping
        c.execute('''UPDATE folder_mappings
                    SET category = ?, message_count = ?, last_checked = CURRENT_TIMESTAMP
                    WHERE user_email = ? AND folder_name = ?''',
                 (category, message_count, user_email, folder_name))
    else:
        # Insert new mapping
        c.execute('''INSERT INTO folder_mappings
                    (user_email, folder_name, category, auto_discovered, message_count)
                    VALUES (?, ?, ?, ?, ?)''',
                 (user_email, folder_name, category, auto_discovered, message_count))
        print(f"✨ New folder discovered: '{folder_name}' → category '{category}' for {user_email}")

    conn.commit()
    conn.close()

def get_folders_for_user(user_email: str) -> List[Tuple[str, str]]:
    """Get all (category, folder_name) pairs for a user

    Returns:
        List of (category, folder_name) tuples
    """
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT category, folder_name FROM folder_mappings
                WHERE user_email = ?
                ORDER BY category''', (user_email,))
    rows = c.fetchall()
    conn.close()
    return rows
