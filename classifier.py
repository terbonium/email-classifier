import torch
import pickle
import os
import warnings
import threading
from transformers import AutoTokenizer, AutoModel
from sklearn.linear_model import LogisticRegression
from email import message_from_string
from email.utils import parseaddr
import time
import config

# Suppress HuggingFace warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='huggingface_hub')

class EmailClassifier:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained('distilbert-base-uncased')
        self.bert_model = AutoModel.from_pretrained('distilbert-base-uncased')
        self.classifier = None
        self.model_path = f'{config.MODEL_DIR}/classifier.pkl'
        
        # Create model directory
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        
        # Load existing model if available
        if os.path.exists(self.model_path):
            self.load_model()
        else:
            self.classifier = LogisticRegression(max_iter=1000, multi_class='multinomial')
    
    def extract_features(self, text: str) -> torch.Tensor:
        """Extract features from text using DistilBERT"""
        inputs = self.tokenizer(text, return_tensors='pt', truncation=True, 
                               max_length=512, padding=True)
        
        with torch.no_grad():
            outputs = self.bert_model(**inputs)
            # Use [CLS] token embedding as text representation
            features = outputs.last_hidden_state[:, 0, :].squeeze()
        
        return features.numpy()
    
    def parse_email(self, raw_email: str) -> tuple:
        """Parse email and extract relevant text"""
        msg = message_from_string(raw_email)
        
        # Extract subject
        subject = msg.get('subject', '')
        
        # Extract body
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        # Extract sender
        from_addr = parseaddr(msg.get('from', ''))[1]
        
        # Combine subject and body (first 1000 chars of body)
        text = f"{subject} {body[:1000]}"
        
        message_id = msg.get('message-id', '')
        
        return text, subject, from_addr, message_id, msg
    
    def apply_sender_heuristics(self, from_addr: str, probabilities: list) -> list:
        """Apply sender-based heuristics to adjust classification probabilities"""
        adjusted_probs = probabilities.copy()

        # Extract domain from sender email
        domain = from_addr.lower().split('@')[-1] if '@' in from_addr else ''

        # Government and civic organization domains should be classified as personal, not shopping
        civic_domains = ['.gov', '.edu', '.org']
        civic_keywords = ['government', 'county', 'city', 'state', 'municipal', 'district', 'commissioner']

        is_civic = False

        # Check domain
        for civic_domain in civic_domains:
            if domain.endswith(civic_domain):
                is_civic = True
                break

        # Check if domain contains civic keywords
        if not is_civic:
            for keyword in civic_keywords:
                if keyword in domain:
                    is_civic = True
                    break

        # If civic email, strongly bias away from shopping toward personal
        if is_civic and 'shopping' in config.CATEGORIES:
            shopping_idx = config.CATEGORIES.index('shopping')
            personal_idx = config.CATEGORIES.index('personal') if 'personal' in config.CATEGORIES else 0

            # Reduce shopping probability by 80%
            shopping_prob = adjusted_probs[shopping_idx]
            adjusted_probs[shopping_idx] = shopping_prob * 0.2

            # Add the reduced probability to personal
            adjusted_probs[personal_idx] += shopping_prob * 0.8

            # Normalize
            total = sum(adjusted_probs)
            adjusted_probs = [p / total for p in adjusted_probs]

        return adjusted_probs

    def classify(self, raw_email: str, user_email: str = None) -> tuple:
        """Classify an email and return category, confidence, processing time"""
        start_time = time.time()

        text, subject, from_addr, message_id, msg = self.parse_email(raw_email)
        features = self.extract_features(text)

        if self.classifier is None or not hasattr(self.classifier, 'classes_'):
            # No trained model yet, default to personal
            processing_time = time.time() - start_time
            return 'personal', 0.5, processing_time, message_id, subject

        # Predict
        prediction = self.classifier.predict([features])[0]
        probabilities = self.classifier.predict_proba([features])[0]

        # Apply sender-based heuristics
        probabilities = self.apply_sender_heuristics(from_addr, probabilities)

        # Apply user weights if available
        if user_email:
            weights = config.get_user_weights(user_email)
            weighted_probs = []
            for i, category in enumerate(config.CATEGORIES):
                weighted_probs.append(probabilities[i] * weights.get(category, 1.0))

            # Normalize
            total = sum(weighted_probs)
            weighted_probs = [p / total for p in weighted_probs]

            # Get prediction from weighted probabilities
            max_idx = weighted_probs.index(max(weighted_probs))
            prediction = config.CATEGORIES[max_idx]
            confidence = weighted_probs[max_idx]
        else:
            # Get prediction from heuristics-adjusted probabilities
            max_idx = probabilities.tolist().index(max(probabilities))
            prediction = config.CATEGORIES[max_idx]
            confidence = max(probabilities)

        processing_time = time.time() - start_time

        return prediction, confidence, processing_time, message_id, subject
    
    def train(self, texts: list, labels: list):
        """Train the classifier with email texts and labels"""
        if len(texts) < len(config.CATEGORIES):
            print("Not enough training data yet")
            return False

        print(f"Training on {len(texts)} emails...")
        start_time = time.time()

        # Extract features for all texts
        print("  Extracting features...")
        features = [self.extract_features(text) for text in texts]
        feature_time = time.time() - start_time
        print(f"  Feature extraction completed in {feature_time:.2f}s")

        # Train with timeout
        print("  Training model...")
        training_result = {'success': False, 'error': None}

        def train_worker():
            try:
                self.classifier.fit(features, labels)
                training_result['success'] = True
            except Exception as e:
                training_result['error'] = str(e)

        thread = threading.Thread(target=train_worker)
        thread.daemon = True
        thread.start()
        thread.join(timeout=config.MAX_TRAINING_TIME_SECONDS)

        if thread.is_alive():
            print(f"  ⚠️  Training timeout after {config.MAX_TRAINING_TIME_SECONDS}s - model training aborted")
            return False

        if not training_result['success']:
            error = training_result.get('error', 'Unknown error')
            print(f"  ✗ Training failed: {error}")
            return False

        training_time = time.time() - start_time
        self.save_model()
        print(f"  ✓ Training complete in {training_time:.2f}s")
        return True
    
    def save_model(self):
        """Save the trained classifier"""
        with open(self.model_path, 'wb') as f:
            pickle.dump(self.classifier, f)
    
    def load_model(self):
        """Load a trained classifier"""
        try:
            with open(self.model_path, 'rb') as f:
                self.classifier = pickle.load(f)
            print("Loaded existing model")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.classifier = LogisticRegression(max_iter=1000, multi_class='multinomial')
