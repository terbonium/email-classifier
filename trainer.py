import imapclient
import email
from email.header import decode_header
import time
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
    
    def discover_folders(self):
        """Discover and register new IMAP folders for all users

        Scans all IMAP folders and automatically adds new ones with messages
        to the folder_mappings table for training.
        """
        print("\n=== Discovering IMAP folders ===")

        # System folders to exclude from auto-discovery
        excluded_folders = {
            'Trash', 'Deleted', 'Deleted Messages', 'Deleted Items',
            'Drafts', 'Sent', 'Sent Messages', 'Sent Items',
            'Archive', 'All Mail', '[Gmail]/All Mail',
            '[Gmail]/Trash', '[Gmail]/Spam', '[Gmail]/Sent Mail',
            '[Gmail]/Drafts', '[Gmail]/Important', '[Gmail]/Starred'
        }

        for user_email, password in config.IMAP_USERS:
            print(f"Scanning folders for {user_email}...")

            try:
                client = imapclient.IMAPClient(config.IMAP_HOST, port=config.IMAP_PORT, ssl=True)
                client.login(user_email, password)

                # Get existing folder mappings for this user
                existing_folders = {folder for _, folder in config.get_folders_for_user(user_email)}

                # List all folders
                folders = client.list_folders()

                for flags, delimiter, folder_name in folders:
                    # Skip excluded system folders
                    if folder_name in excluded_folders:
                        continue

                    # Skip folders with NoSelect flag (can't contain messages)
                    if b'\\Noselect' in flags:
                        continue

                    # Check if folder has messages and is not already mapped
                    try:
                        client.select_folder(folder_name, readonly=True)
                        messages = client.search(['ALL'])
                        message_count = len(messages)

                        if message_count > 0 and folder_name not in existing_folders:
                            # New folder with messages - add to mappings
                            config.add_folder_mapping(
                                user_email=user_email,
                                folder_name=folder_name,
                                category=None,  # Auto-generate from folder name
                                auto_discovered=True,
                                message_count=message_count
                            )
                        elif folder_name in existing_folders:
                            # Update message count for existing folder
                            config.add_folder_mapping(
                                user_email=user_email,
                                folder_name=folder_name,
                                auto_discovered=False,
                                message_count=message_count
                            )

                    except Exception as e:
                        # Some folders may not be selectable, skip them
                        pass

                client.logout()
                print(f"  ✓ Folder discovery complete for {user_email}")

            except Exception as e:
                print(f"  Error during folder discovery for {user_email}: {e}")

        print("=== Folder discovery complete ===\n")

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

                # Get folder mappings for this user
                folder_mappings = config.get_folders_for_user(user_email)

                if not folder_mappings:
                    print(f"  No folder mappings found for {user_email}, skipping...")
                    client.logout()
                    continue

                # Fetch from each category folder
                category_counts = {}

                # First pass: count messages in each folder
                for category, folder in folder_mappings:
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
                for category, folder in folder_mappings:
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
                            message_id = msg.get('message-id', f'msg-{msg_id}')
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

                # Get folder mappings for this user
                folder_mappings = config.get_folders_for_user(user_email)

                if not folder_mappings:
                    print(f"  No folder mappings found for {user_email}, skipping...")
                    client.logout()
                    continue

                # Get all message IDs from training data for this user
                c.execute('SELECT message_id, category FROM training_data WHERE user_email = ?',
                         (user_email,))
                known_messages = {row[0]: row[1] for row in c.fetchall()}

                # Check current location of each message
                for category, folder in folder_mappings:
                    try:
                        client.select_folder(folder, readonly=True)
                        messages = client.search(['ALL'])
                        
                        for msg_id in messages:
                            raw_msg = client.fetch([msg_id], ['RFC822'])
                            email_body = raw_msg[msg_id][b'RFC822'].decode('utf-8', errors='ignore')
                            msg = email.message_from_string(email_body)
                            message_id = msg.get('message-id', '')
                            
                            # If this message was in our training data but in a different category
                            if message_id in known_messages and known_messages[message_id] != category:
                                old_category = known_messages[message_id]
                                subject = self.decode_subject(msg.get('subject', ''))
                                
                                print(f"  📧 Reclassification: {old_category} → {category}")
                                print(f"     Subject: {subject[:60]}...")
                                
                                # Log the reclassification
                                config.log_reclassification(
                                    message_id, user_email, subject,
                                    old_category, category
                                )
                                
                                # Update category in database
                                c.execute('UPDATE training_data SET category = ? WHERE message_id = ?',
                                         (category, message_id))
                                updated += 1
                    
                    except Exception as e:
                        print(f"  Error checking folder {folder}: {e}")
                
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

        # Get current categories
        current_categories = config.get_all_categories()

        if len(rows) < len(current_categories):
            print("Not enough training data to retrain")
            return False
        
        texts = [row[0] for row in rows]
        labels = [row[1] for row in rows]
        
        print(f"Retraining with {len(texts)} messages...")
        success = self.classifier.train(texts, labels)
        
        conn.close()
        return success
    
    def training_loop(self):
        """Main training loop"""
        print("Starting training loop...")

        # Discover folders first
        self.discover_folders()

        # Initial training
        print("Fetching initial training data...")
        texts, labels = self.fetch_training_data()

        # Get current categories
        current_categories = config.get_all_categories()

        if len(texts) >= len(current_categories):
            print(f"Initial training with {len(texts)} messages across {len(current_categories)} categories...")
            self.classifier.train(texts, labels)
        else:
            print("Insufficient initial training data")

        # Periodic retraining
        while True:
            time.sleep(config.TRAINING_INTERVAL)

            print("\n=== Periodic maintenance ===")

            # Discover new folders
            self.discover_folders()

            # Check for reclassifications
            print("\n=== Checking for reclassifications ===")
            updated = self.check_reclassifications()

            if updated > 0:
                print(f"Found {updated} reclassifications, retraining...")
                self.retrain()
            else:
                # Even if no reclassifications, check if new folders were discovered
                new_categories = config.get_all_categories()
                if len(new_categories) > len(current_categories):
                    print(f"New categories discovered! Training on new folders...")
                    texts, labels = self.fetch_training_data()
                    if len(texts) > 0:
                        self.classifier.train(texts, labels)
                    current_categories = new_categories
                else:
                    print("No reclassifications or new folders found")
