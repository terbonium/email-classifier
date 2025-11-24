import asyncio
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP as SMTPProtocol
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import message_from_string
from email.generator import Generator
from io import StringIO
import config
from classifier import EmailClassifier


def create_footer_text(classification_id, category, confidence):
    """Create plain text footer for email"""
    url = f"{config.CLASSIFIER_UI_BASE_URL}?open_classification={classification_id}"
    return f"""

---
Email Classification: {category.upper()} ({confidence*100:.1f}% confidence)
View details & modify classification: {url}
"""


def create_footer_html(classification_id, category, confidence):
    """Create HTML footer for email"""
    url = f"{config.CLASSIFIER_UI_BASE_URL}?open_classification={classification_id}"

    # Color mapping for categories
    colors = {
        'personal': '#2196F3',
        'shopping': '#FF9800',
        'spam': '#F44336'
    }
    color = colors.get(category, '#666')

    return f"""
<div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #ddd; font-family: Arial, sans-serif; font-size: 12px; color: #666;">
    <p style="margin: 0 0 8px 0;">
        <strong>Email Classification:</strong>
        <span style="background: {color}; color: white; padding: 2px 8px; border-radius: 3px; font-weight: bold;">
            {category.upper()}
        </span>
        <span style="margin-left: 8px;">({confidence*100:.1f}% confidence)</span>
    </p>
    <p style="margin: 0;">
        <a href="{url}" style="color: #2196F3; text-decoration: none;">
            View details &amp; modify classification
        </a>
    </p>
</div>
"""


def add_footer_to_email(msg, classification_id, category, confidence):
    """Add footer to email message, handling various MIME types"""
    footer_text = create_footer_text(classification_id, category, confidence)
    footer_html = create_footer_html(classification_id, category, confidence)

    if msg.is_multipart():
        # Handle multipart messages
        for part in msg.walk():
            content_type = part.get_content_type()

            if content_type == 'text/plain' and not part.is_multipart():
                # Add text footer to plain text part
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        text = payload.decode(charset, errors='ignore')
                        text += footer_text
                        part.set_payload(text, charset)
                except Exception as e:
                    print(f"  Warning: Could not add footer to text part: {e}")

            elif content_type == 'text/html' and not part.is_multipart():
                # Add HTML footer to HTML part
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        html = payload.decode(charset, errors='ignore')

                        # Insert before closing body tag, or append to end
                        if '</body>' in html.lower():
                            # Find the closing body tag (case-insensitive)
                            import re
                            html = re.sub(
                                r'(</body>)',
                                footer_html + r'\1',
                                html,
                                flags=re.IGNORECASE,
                                count=1
                            )
                        else:
                            html += footer_html

                        part.set_payload(html, charset)
                except Exception as e:
                    print(f"  Warning: Could not add footer to HTML part: {e}")
    else:
        # Handle single-part messages
        content_type = msg.get_content_type()

        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                content = payload.decode(charset, errors='ignore')

                if content_type == 'text/html':
                    # Insert before closing body tag, or append
                    if '</body>' in content.lower():
                        import re
                        content = re.sub(
                            r'(</body>)',
                            footer_html + r'\1',
                            content,
                            flags=re.IGNORECASE,
                            count=1
                        )
                    else:
                        content += footer_html
                else:
                    # Default to plain text
                    content += footer_text

                msg.set_payload(content, charset)
        except Exception as e:
            print(f"  Warning: Could not add footer to message: {e}")

    return msg


def message_to_string(msg):
    """Convert email message object back to string"""
    fp = StringIO()
    g = Generator(fp, mangle_from_=False)
    g.flatten(msg)
    return fp.getvalue()

class ClassifierHandler:
    def __init__(self, classifier: EmailClassifier):
        self.classifier = classifier
    
    async def handle_DATA(self, server, session, envelope):
        """Handle incoming email for classification"""
        print(f"\nReceived email from {envelope.mail_from} to {envelope.rcpt_tos}")

        # Get raw email content
        raw_email = envelope.content.decode('utf-8', errors='ignore')

        # Determine user email from recipient
        user_email = envelope.rcpt_tos[0] if envelope.rcpt_tos else None

        # First, parse the email to extract message_id for deduplication check
        text, subject, from_addr, message_id, msg = self.classifier.parse_email(raw_email)

        # Check if this message has already been classified
        existing = config.get_existing_classification(message_id, user_email)

        if existing:
            # Use existing classification to avoid duplicate processing
            category = existing['category']
            confidence = existing['confidence']
            proc_time = existing['processing_time']
            print(f"  ✓ Using existing classification (deduplication)")
            print(f"  Classification: {category} (confidence: {confidence:.2f}, cached)")
            print(f"  Subject: {subject}")

            # For existing classifications, get the classification ID from the database
            classification_id = None
            conn = config.get_db()
            c = conn.cursor()
            c.execute('''SELECT id FROM classifications
                        WHERE message_id = ? AND user_email = ?
                        ORDER BY timestamp DESC LIMIT 1''',
                      (message_id, user_email))
            row = c.fetchone()
            if row:
                classification_id = row[0]
            conn.close()
        else:
            # Classify the email
            category, confidence, proc_time, message_id, subject, probabilities, sender_domain = self.classifier.classify(
                raw_email, user_email
            )

            print(f"  Classification: {category} (confidence: {confidence:.2f}, time: {proc_time:.3f}s)")
            print(f"  Subject: {subject}")

            # Log classification (only for new classifications) with full probability breakdown
            classification_id = config.log_classification(
                message_id, user_email or 'unknown', subject,
                category, confidence, proc_time,
                probabilities, sender_domain
            )

            # Add to training data so reclassifications can be detected
            config.add_to_training_data(
                message_id, user_email or 'unknown', subject, text, category
            )

        # Add classification headers to email
        lines = raw_email.split('\n')
        header_end = 0
        for i, line in enumerate(lines):
            if line.strip() == '':
                header_end = i
                break

        # Insert classification headers
        lines.insert(header_end, f'X-Email-Category: {category}')
        lines.insert(header_end + 1, f'X-Classification-Confidence: {confidence:.3f}')
        lines.insert(header_end + 2, f'X-Classifier-Time: {proc_time:.3f}')

        modified_email = '\n'.join(lines)

        # Add footer with classification link if enabled
        if config.FOOTER_ENABLED and classification_id:
            try:
                # Parse the modified email
                modified_msg = message_from_string(modified_email)

                # Add footer to the message body
                modified_msg = add_footer_to_email(modified_msg, classification_id, category, confidence)

                # Convert back to string
                modified_email = message_to_string(modified_msg)
                print(f"  ✓ Added classifier footer with link to classification #{classification_id}")
            except Exception as e:
                print(f"  Warning: Could not add footer to email: {e}")
        
        # Deliver via SMTP to mail server
        try:
            smtp = smtplib.SMTP(config.DELIVERY_HOST, config.DELIVERY_PORT)
            
            # Use STARTTLS if configured
            if config.DELIVERY_USE_TLS:
                smtp.starttls()
            
            # Authenticate if credentials provided
            if config.DELIVERY_USER and config.DELIVERY_PASSWORD:
                smtp.login(config.DELIVERY_USER, config.DELIVERY_PASSWORD)
            
            # Send the classified email
            smtp.sendmail(
                envelope.mail_from,
                envelope.rcpt_tos,
                modified_email.encode('utf-8')
            )
            smtp.quit()
            
            print(f"  ✓ Delivered to {config.DELIVERY_HOST}:{config.DELIVERY_PORT}")
            return '250 Message accepted for delivery'
            
        except Exception as e:
            print(f"  ✗ Delivery error: {e}")
            return f'451 Temporary failure: {str(e)}'

class ClassifierSMTP:
    def __init__(self, classifier: EmailClassifier, host='0.0.0.0', port=2525):
        self.classifier = classifier
        self.host = host
        self.port = port
        self.controller = None
    
    def start(self):
        """Start the SMTP server"""
        handler = ClassifierHandler(self.classifier)
        self.controller = Controller(handler, hostname=self.host, port=self.port)
        self.controller.start()
        print(f"SMTP classifier listening on {self.host}:{self.port}")
        print(f"Delivering to {config.DELIVERY_HOST}:{config.DELIVERY_PORT}")
    
    def stop(self):
        """Stop the SMTP server"""
        if self.controller:
            self.controller.stop()
