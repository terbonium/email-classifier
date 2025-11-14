import torch
import pickle
import os
import warnings
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
        
        # Apply user weights if available
        if user_email:
            weights = config.get_user_weights(user_email)
            # Get classes from the trained model
            model_classes = list(self.classifier.classes_)
            weighted_probs = []
            for i, category in enumerate(model_classes):
                weighted_probs.append(probabilities[i] * weights.get(category, 1.0))

            # Normalize
            total = sum(weighted_probs)
            weighted_probs = [p / total for p in weighted_probs]

            # Get prediction from weighted probabilities
            max_idx = weighted_probs.index(max(weighted_probs))
            prediction = model_classes[max_idx]
            confidence = weighted_probs[max_idx]
        else:
            confidence = max(probabilities)
        
        processing_time = time.time() - start_time
        
        return prediction, confidence, processing_time, message_id, subject
    
    def train(self, texts: list, labels: list):
        """Train the classifier with email texts and labels"""
        # Get unique categories from labels
        unique_categories = set(labels)

        if len(texts) < len(unique_categories):
            print("Not enough training data yet")
            return False

        print(f"Training on {len(texts)} emails across {len(unique_categories)} categories...")
        features = [self.extract_features(text) for text in texts]

        self.classifier.fit(features, labels)
        self.save_model()
        print(f"Training complete - Model knows {len(self.classifier.classes_)} categories: {', '.join(self.classifier.classes_)}")
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
