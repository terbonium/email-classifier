import imapclient
import email
from email.header import decode_header
import time
from datetime import datetime
import config
from classifier import EmailClassifier

class EmailTrainer:
    def __init__(self, classifier: EmailClassifier):
        self.classifier = classifier
    
    def decode_subject(self, subject):
        """Decode email subject"""
        if subject is None:
            return ""
        decoded = decode_header(subject)
        parts = []
        for content, encoding in decoded:
            if isinstance(content, bytes):
                parts.append(content.decode(encoding or 'utf-8', errors='ignore'))
            else:
                parts.append(content)
        return ''.join(parts)
    
    def fetch_training_data(self):
        """Fetch training data from IMAP folders for all configured users"""
        conn = config.get_db()
        c = conn.cursor()
        
        all_texts = []
        all_labels = []
        
        for user_email, password in config.IMAP_USERS:
            print(f"Fetching training data for {user_email}...")
            
            try:
                # Connect to IMAP
                client = imapclient.IMAPClient(config.IMAP_HOST, port=config.IMAP_PORT, ssl=True)
                client.login(user_email, password)
                
                # Fetch from each category folder
                category_counts = {}
                
                # First pass: count messages in each folder
                for category, folder in config.FOLDER_MAP.items():
                    try:
                        client.select_folder(folder, readonly=True)
                        messages = client.search(['ALL'])
                        category_counts[category] = len(messages)
                        print(f"  Found {len(messages)} messages in {folder}")
                    except Exception as e:
                        print(f"  Error checking folder {folder}: {e}")
                        category_counts[category] = 0
                
                # Check for severe imbalance
                min_count = min(category_counts.values()) if category_counts else 0
                max_count = max(category_counts.values()) if category_counts else 0
                
                if min_count > 0 and max_count / min_count > 10:
                    print(f"\n  ⚠️  WARNING: Severe class imbalance detected!")
                    print(f"  ⚠️  {category_counts}")
                    print(f"  ⚠️  Consider using balanced training by setting MAX_TRAINING_EMAILS={min_count}")
                    print(f"  ⚠️  Or add more examples to under-represented categories\n")
                
                # Second pass: fetch actual training data
                for category, folder in config.FOLDER_MAP.items():
                    try:
                        client.select_folder(folder, readonly=True)
                        messages = client.search(['ALL'])
                        
                        # Use configurable limit for training emails per folder
                        limit = config.MAX_TRAINING_EMAILS
                        selected_messages = messages[-limit:] if len(messages) > limit else messages
                        
                        print(f"  Processing {len(selected_messages)} messages from {folder} (limit: {limit})")
                        
                        for msg_id in selected_messages:
                            raw_msg = client.fetch([msg_id], ['RFC822'])
                            email_body = raw_msg[msg_id][b'RFC822'].decode('utf-8', errors='ignore')

                            msg = email.message_from_string(email_body)
                            message_id = msg.get('message-id', '').strip()

                            # Generate fallback Message-ID if missing (unique per user/folder/IMAP-ID)
                            if not message_id:
                                message_id = f'<generated-{user_email}-{folder}-{msg_id}@classifier.local>'

                            subject = self.decode_subject(msg.get('subject', ''))
                            
                            # Extract text
                            body = ''
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == 'text/plain':
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            body += payload.decode('utf-8', errors='ignore')
                            else:
                                payload = msg.get_payload(decode=True)
                                if payload:
                                    body = payload.decode('utf-8', errors='ignore')
                            
                            text = f"{subject} {body[:1000]}"
                            
                            # Store in database
                            c.execute('''INSERT OR REPLACE INTO training_data 
                                        (message_id, user_email, subject, body, category)
                                        VALUES (?, ?, ?, ?, ?)''',
                                     (message_id, user_email, subject, text, category))
                            
                            all_texts.append(text)
                            all_labels.append(category)
                    
                    except Exception as e:
                        print(f"  Error processing folder {folder}: {e}")
                
                client.logout()
                
            except Exception as e:
                print(f"Error connecting to IMAP for {user_email}: {e}")
        
        conn.commit()
        conn.close()
        
        return all_texts, all_labels
    
    def check_reclassifications(self):
        """Check if users have moved emails, indicating reclassification"""
        conn = config.get_db()
        c = conn.cursor()

        updated = 0

        for user_email, password in config.IMAP_USERS:
            print(f"Checking for reclassifications by {user_email}...")

            try:
                client = imapclient.IMAPClient(config.IMAP_HOST, port=config.IMAP_PORT, ssl=True)
                client.login(user_email, password)

                # Get all message IDs from training data for this user
                c.execute('SELECT message_id, category FROM training_data WHERE user_email = ?',
                         (user_email,))
                known_messages = {row[0]: row[1] for row in c.fetchall()}

                # First pass: Build a map of where each message currently is
                # This prevents duplicate processing when a message appears in multiple folders
                current_locations = {}  # message_id -> (category, folder, subject)

                for category, folder in config.FOLDER_MAP.items():
                    try:
                        client.select_folder(folder, readonly=True)
                        messages = client.search(['ALL'])

                        for msg_id in messages:
                            raw_msg = client.fetch([msg_id], ['RFC822'])
                            email_body = raw_msg[msg_id][b'RFC822'].decode('utf-8', errors='ignore')
                            msg = email.message_from_string(email_body)
                            message_id = msg.get('message-id', '').strip()

                            # Skip messages without valid Message-ID to prevent false reclassifications
                            if not message_id:
                                continue

                            # Only track messages that are in our training data
                            if message_id in known_messages:
                                subject = self.decode_subject(msg.get('subject', ''))
                                # Store the current location (last one wins if message is in multiple folders)
                                current_locations[message_id] = (category, folder, subject)

                    except Exception as e:
                        print(f"  Error checking folder {folder}: {e}")

                # Second pass: Process reclassifications based on final locations
                for message_id, (new_category, new_folder, subject) in current_locations.items():
                    old_category = known_messages[message_id]

                    # Only log if the category actually changed
                    if old_category != new_category:
                        old_folder = config.FOLDER_MAP.get(old_category, 'Unknown')

                        print(f"\n  🔄 MESSAGE RECLASSIFICATION DETECTED")
                        print(f"     Message-ID: {message_id}")
                        print(f"     Subject: {subject}")
                        print(f"     Original Category: {old_category} (folder: {old_folder})")
                        print(f"     New Category: {new_category} (folder: {new_folder})")
                        print(f"     User: {user_email}")
                        print(f"     Action: Message moved from '{old_folder}' to '{new_folder}'\n")

                        # Log the reclassification
                        config.log_reclassification(
                            message_id, user_email, subject,
                            old_category, new_category, old_folder, new_folder
                        )

                        # Update category in database
                        try:
                            c.execute('UPDATE training_data SET category = ? WHERE message_id = ?',
                                     (new_category, message_id))
                            updated += 1
                        except Exception as e:
                            print(f"  Error updating database for {message_id}: {e}")

                client.logout()

            except Exception as e:
                print(f"Error connecting to IMAP for {user_email}: {e}")

        conn.commit()
        conn.close()

        if updated > 0:
            print(f"✅ Detected {updated} reclassifications")

        return updated
    
    def retrain(self):
        """Retrain the model with current training data"""
        conn = config.get_db()
        c = conn.cursor()
        
        # Get all training data
        c.execute('SELECT body, category FROM training_data')
        rows = c.fetchall()
        
        if len(rows) < len(config.CATEGORIES):
            print("Not enough training data to retrain")
            return False
        
        texts = [row[0] for row in rows]
        labels = [row[1] for row in rows]
        
        print(f"Retraining with {len(texts)} messages...")
        success = self.classifier.train(texts, labels)
        
        conn.close()
        return success
    
    def training_loop(self):
        """Main training loop with scheduled retraining"""
        print("Starting training loop...")

        # Parse scheduled training time
        try:
            scheduled_hour, scheduled_minute = map(int, config.TRAINING_SCHEDULE.split(':'))
            print(f"Scheduled training time: {scheduled_hour:02d}:{scheduled_minute:02d}")
        except ValueError:
            print(f"⚠️  Invalid TRAINING_SCHEDULE format: {config.TRAINING_SCHEDULE}")
            print("   Using default: 3:00")
            scheduled_hour, scheduled_minute = 3, 0

        # Initial training
        print("Fetching initial training data...")
        texts, labels = self.fetch_training_data()

        if len(texts) >= len(config.CATEGORIES):
            print(f"Initial training with {len(texts)} messages...")
            self.classifier.train(texts, labels)
        else:
            print("Insufficient initial training data")

        # Track last training date to avoid multiple trainings in same day
        last_training_date = datetime.now().date()

        # Periodic retraining check
        while True:
            # Sleep for a shorter interval to check time more frequently
            time.sleep(60)  # Check every minute

            now = datetime.now()
            current_time = now.time()
            current_date = now.date()

            # Check if it's the scheduled time and we haven't trained today yet
            if (current_time.hour == scheduled_hour and
                current_time.minute == scheduled_minute and
                current_date != last_training_date):

                print(f"\n=== Scheduled Training at {now.strftime('%Y-%m-%d %H:%M:%S')} ===")
                print("Checking for reclassifications...")
                updated = self.check_reclassifications()

                if updated > 0:
                    print(f"Found {updated} reclassifications, retraining...")
                    self.retrain()
                else:
                    print("No reclassifications found, retraining with existing data...")
                    self.retrain()

                # Update last training date
                last_training_date = current_date
                print(f"Next scheduled training: {current_date.replace(day=current_date.day+1)} at {scheduled_hour:02d}:{scheduled_minute:02d}")

            # Also support interval-based checks for immediate reclassifications
            # Check every TRAINING_INTERVAL seconds for user-triggered retraining
            if hasattr(self, 'last_interval_check'):
                if time.time() - self.last_interval_check >= config.TRAINING_INTERVAL:
                    print("\n=== Interval-based reclassification check ===")
                    updated = self.check_reclassifications()
                    if updated > 0:
                        print(f"Found {updated} reclassifications outside scheduled time")
                    self.last_interval_check = time.time()
            else:
                self.last_interval_check = time.time()
