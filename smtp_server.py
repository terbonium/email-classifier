import asyncio
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP as SMTPProtocol
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import message_from_string
import config
from classifier import EmailClassifier

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
        else:
            # Classify the email
            category, confidence, proc_time, message_id, subject = self.classifier.classify(
                raw_email, user_email
            )

            print(f"  Classification: {category} (confidence: {confidence:.2f}, time: {proc_time:.3f}s)")
            print(f"  Subject: {subject}")

            # Log classification (only for new classifications)
            config.log_classification(
                message_id, user_email or 'unknown', subject,
                category, confidence, proc_time
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
