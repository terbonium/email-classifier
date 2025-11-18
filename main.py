#!/usr/bin/env python3
import threading
import time
import config
from classifier import EmailClassifier
from trainer import EmailTrainer
from smtp_server import ClassifierSMTP
from web_ui import run_web_ui

def main():
    print("Starting Email Classifier System...")
    
    # Initialize database
    config.init_db()
    
    # Initialize classifier
    classifier = EmailClassifier()
    
    # Initialize trainer
    trainer = EmailTrainer(classifier)
    
    # Start SMTP server in a thread
    smtp_server = ClassifierSMTP(classifier)
    smtp_thread = threading.Thread(target=smtp_server.start, daemon=True)
    smtp_thread.start()
    
    # Start training loop in a thread
    training_thread = threading.Thread(target=trainer.training_loop, daemon=True)
    training_thread.start()
    
    # Give services a moment to start
    time.sleep(2)
    
    print("\n" + "="*60)
    print("Email Classifier System Running")
    print("="*60)
    print(f"SMTP Server: localhost:2525")
    print(f"Web Dashboard: http://localhost:8080")
    print(f"Training interval: {config.TRAINING_INTERVAL} seconds")
    print(f"Configured users: {len(config.IMAP_USERS)}")
    print("="*60 + "\n")

    # Start web UI (blocking)
    run_web_ui(trainer=trainer, classifier=classifier)

if __name__ == '__main__':
    main()
