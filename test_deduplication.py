#!/usr/bin/env python3
"""
Test script to verify email deduplication works correctly
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

def send_test_email(to_addr, subject, body, message_id, smtp_host='localhost', smtp_port=2525):
    """Send a test email with a specific message ID"""
    msg = MIMEMultipart()
    msg['From'] = 'test@example.com'
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg['Message-ID'] = message_id

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.send_message(msg)
        server.quit()
        print(f"✓ Sent: {subject} (Message-ID: {message_id})")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == '__main__':
    print("Testing email deduplication...\n")

    # Test 1: Send the same email twice
    print("Test 1: Sending the same email twice (should use cached classification on second)")
    test_message_id = '<test-dedup-001@example.com>'
    test_subject = 'Test Email for Deduplication'
    test_body = 'This is a test email to verify deduplication works correctly.'

    # First send
    print("\n1. First send (should classify):")
    send_test_email('user@example.com', test_subject, test_body, test_message_id)

    time.sleep(2)  # Wait a bit

    # Second send (duplicate)
    print("\n2. Second send (should use cached classification):")
    send_test_email('user@example.com', test_subject, test_body, test_message_id)

    time.sleep(2)

    # Third send (another duplicate)
    print("\n3. Third send (should use cached classification):")
    send_test_email('user@example.com', test_subject, test_body, test_message_id)

    print("\n" + "="*60)
    print("Test complete!")
    print("Check the SMTP server logs to verify:")
    print("  - First email: 'Classification: ...'")
    print("  - Second/Third emails: '✓ Using existing classification (deduplication)'")
    print("="*60)
