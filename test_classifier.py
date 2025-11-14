#!/usr/bin/env python3
"""
Simple test script to send test emails to the classifier
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_test_email(to_addr, subject, body, smtp_host='localhost', smtp_port=2525):
    """Send a test email to the classifier"""
    msg = MIMEMultipart()
    msg['From'] = 'test@example.com'
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg['Message-ID'] = f'<test-{hash(subject)}-{hash(body)}@example.com>'
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.send_message(msg)
        server.quit()
        print(f"✓ Sent: {subject}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == '__main__':
    # Test emails for different categories
    tests = [
        {
            'to': 'user@example.com',
            'subject': 'Re: Meeting tomorrow',
            'body': 'Hi John, yes I can make the meeting at 3pm. See you tomorrow!'
        },
        {
            'to': 'user@example.com',
            'subject': 'Your Amazon Order Has Shipped',
            'body': 'Your order #123-456789 has been shipped. Track your package here. Estimated delivery: 2 days.'
        },
        {
            'to': 'user@example.com',
            'subject': 'URGENT: Claim your prize NOW!!!',
            'body': 'You have won $1,000,000! Click here immediately to claim. This is not a scam!!!'
        },
        {
            'to': 'user@example.com',
            'subject': 'Weekly Project Update',
            'body': 'Here is the weekly update on our project status. All milestones are on track.'
        },
        {
            'to': 'user@example.com',
            'subject': '50% OFF Sale - Today Only!',
            'body': 'Flash sale! Get 50% off all items. Shop now before it ends. Limited time offer.'
        }
    ]
    
    print("Sending test emails to classifier...\n")
    
    for test in tests:
        send_test_email(test['to'], test['subject'], test['body'])
    
    print("\nTest emails sent. Check the web dashboard at http://localhost:8080")
