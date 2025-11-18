from flask import Flask, render_template_string, jsonify, request
import config
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

# Global references to trainer and classifier (set by run_web_ui)
_trainer = None
_classifier = None

# HTML template
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Email Classifier Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th {
            background: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }
        td {
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background: #f5f5f5;
        }
        .category {
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
        }
        .personal { background: #2196F3; color: white; }
        .shopping { background: #FF9800; color: white; }
        .spam { background: #F44336; color: white; }
        .confidence {
            font-weight: bold;
        }
        .high { color: #4CAF50; }
        .medium { color: #FF9800; }
        .low { color: #F44336; }
        .refresh {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-right: 10px;
        }
        .refresh:hover {
            background: #45a049;
        }
        .button-group {
            margin: 20px 0;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn-action {
            background: #2196F3;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .btn-action:hover {
            background: #0b7dda;
        }
        .btn-warning {
            background: #FF9800;
        }
        .btn-warning:hover {
            background: #e68900;
        }
        .btn-action:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .model-stats-card {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #2196F3;
            margin: 20px 0;
        }
        .model-stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }
        .model-stat-item {
            background: white;
            padding: 10px;
            border-radius: 4px;
        }
        .model-stat-label {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
        }
        .model-stat-value {
            font-size: 16px;
            font-weight: bold;
            color: #2196F3;
        }
        .toast {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 15px 20px;
            border-radius: 4px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            display: none;
            z-index: 1000;
        }
        .toast.error {
            background: #F44336;
        }
        .toast.show {
            display: block;
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        .reclassification {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .arrow {
            font-size: 20px;
            color: #666;
        }
        .badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            background: #e8f5e9;
            color: #2e7d32;
            margin-left: 10px;
        }
    </style>
    <script>
        function refresh() {
            location.reload();
        }
        setInterval(refresh, 30000); // Auto-refresh every 30 seconds

        function showToast(message, isError = false) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast show' + (isError ? ' error' : '');
            setTimeout(() => {
                toast.className = 'toast';
            }, 3000);
        }

        function refreshIMAP() {
            const btn = document.getElementById('btn-refresh-imap');
            btn.disabled = true;
            btn.textContent = 'Refreshing...';

            fetch('/api/refresh-imap', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('IMAP refresh started. Check console for progress.');
                    } else {
                        showToast('Error: ' + (data.error || 'Unknown error'), true);
                    }
                    setTimeout(() => {
                        btn.disabled = false;
                        btn.textContent = 'Check for Reclassified Emails';
                    }, 2000);
                })
                .catch(error => {
                    showToast('Network error: ' + error.message, true);
                    btn.disabled = false;
                    btn.textContent = 'Check for Reclassified Emails';
                });
        }

        function retrainModel() {
            const btn = document.getElementById('btn-retrain');
            btn.disabled = true;
            btn.textContent = 'Retraining...';

            fetch('/api/retrain', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('Model retraining started. This may take a few minutes.');
                    } else {
                        showToast('Error: ' + (data.error || 'Unknown error'), true);
                    }
                    setTimeout(() => {
                        btn.disabled = false;
                        btn.textContent = 'Retrain Model';
                        location.reload(); // Reload to show new stats
                    }, 5000);
                })
                .catch(error => {
                    showToast('Network error: ' + error.message, true);
                    btn.disabled = false;
                    btn.textContent = 'Retrain Model';
                });
        }
    </script>
</head>
<body>
    <div id="toast" class="toast"></div>
    <div class="container">
        <h1>📧 Email Classifier Dashboard</h1>

        <div class="button-group">
            <button class="refresh" onclick="refresh()">Refresh Dashboard</button>
            <button id="btn-refresh-imap" class="btn-action" onclick="refreshIMAP()">🔄 Check for Reclassified Emails</button>
            <button id="btn-retrain" class="btn-action btn-warning" onclick="retrainModel()">🤖 Retrain Model</button>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Total Processed</div>
                <div class="stat-value">{{ stats.total }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Personal</div>
                <div class="stat-value">{{ stats.personal }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Shopping</div>
                <div class="stat-value">{{ stats.shopping }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Spam</div>
                <div class="stat-value">{{ stats.spam }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Processing</div>
                <div class="stat-value">{{ "%.3f"|format(stats.avg_time) }}s</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Training Samples</div>
                <div class="stat-value">{{ stats.training_count }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Reclassifications</div>
                <div class="stat-value">{{ stats.reclassifications }}<span class="badge">Learning!</span></div>
            </div>
        </div>

        {% if model_stats %}
        <div class="model-stats-card">
            <h3 style="margin-top: 0; color: #2196F3;">🤖 Model Statistics</h3>
            <div class="model-stats-grid">
                <div class="model-stat-item">
                    <div class="model-stat-label">Model Type</div>
                    <div class="model-stat-value">{{ model_stats.model_name }}</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Training Samples</div>
                    <div class="model-stat-value">{{ model_stats.num_samples }}</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Training Time</div>
                    <div class="model-stat-value">{{ "%.2f"|format(model_stats.training_time) }}s</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Feature Extraction</div>
                    <div class="model-stat-value">{{ "%.2f"|format(model_stats.feature_time) }}s</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Feature Dimensions</div>
                    <div class="model-stat-value">{{ model_stats.num_features }}</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Classes</div>
                    <div class="model-stat-value">{{ model_stats.num_classes }}</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Coefficients</div>
                    <div class="model-stat-value">{{ model_stats.num_coefficients }}</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Model Size</div>
                    <div class="model-stat-value">{{ "%.1f"|format(model_stats.model_size / 1024) }} KB</div>
                </div>
                <div class="model-stat-item">
                    <div class="model-stat-label">Last Trained</div>
                    <div class="model-stat-value" style="font-size: 13px;">{{ model_stats.last_trained }}</div>
                </div>
            </div>
        </div>
        {% else %}
        <div class="model-stats-card">
            <h3 style="margin-top: 0; color: #2196F3;">🤖 Model Statistics</h3>
            <p style="color: #666;">No model has been trained yet. Click "Retrain Model" to train the initial model.</p>
        </div>
        {% endif %}

        {% if recent_reclassifications %}
        <h2>🔄 Recent Reclassifications (Last 20)</h2>
        <p style="color: #666; font-size: 14px;">Emails you moved between folders - the model learns from these!</p>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>User</th>
                    <th>Subject</th>
                    <th>Movement</th>
                </tr>
            </thead>
            <tbody>
                {% for reclass in recent_reclassifications %}
                <tr>
                    <td>{{ reclass.timestamp }}</td>
                    <td>{{ reclass.user_email }}</td>
                    <td>{{ reclass.subject[:60] }}...</td>
                    <td>
                        <div class="reclassification">
                            <span class="category {{ reclass.old_category }}">{{ reclass.old_category }}</span>
                            <span class="arrow">→</span>
                            <span class="category {{ reclass.new_category }}">{{ reclass.new_category }}</span>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}
        
        <h2>Recent Classifications (Last 50)</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>User</th>
                    <th>Subject</th>
                    <th>Category</th>
                    <th>Confidence</th>
                    <th>Time (s)</th>
                </tr>
            </thead>
            <tbody>
                {% for record in recent %}
                <tr>
                    <td>{{ record.timestamp }}</td>
                    <td>{{ record.user_email }}</td>
                    <td>{{ record.subject[:60] }}...</td>
                    <td><span class="category {{ record.predicted_category }}">{{ record.predicted_category }}</span></td>
                    <td>
                        <span class="confidence {% if record.confidence > 0.8 %}high{% elif record.confidence > 0.6 %}medium{% else %}low{% endif %}">
                            {{ "%.2f"|format(record.confidence) }}
                        </span>
                    </td>
                    <td>{{ "%.3f"|format(record.processing_time) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <h2>Training Data Distribution</h2>
        <table>
            <thead>
                <tr>
                    <th>User</th>
                    <th>Personal</th>
                    <th>Shopping</th>
                    <th>Spam</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                {% for user_dist in training_dist %}
                <tr>
                    <td>{{ user_dist.user }}</td>
                    <td>{{ user_dist.personal }}</td>
                    <td>{{ user_dist.shopping }}</td>
                    <td>{{ user_dist.spam }}</td>
                    <td><strong>{{ user_dist.total }}</strong></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard"""
    conn = config.get_db()
    c = conn.cursor()
    
    # Get overall stats
    c.execute('SELECT COUNT(*) FROM classifications')
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM classifications WHERE predicted_category = 'personal'")
    personal = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM classifications WHERE predicted_category = 'shopping'")
    shopping = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM classifications WHERE predicted_category = 'spam'")
    spam = c.fetchone()[0]
    
    c.execute('SELECT AVG(processing_time) FROM classifications')
    avg_time = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(*) FROM training_data')
    training_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM reclassifications')
    reclassifications = c.fetchone()[0]
    
    stats = {
        'total': total,
        'personal': personal,
        'shopping': shopping,
        'spam': spam,
        'avg_time': avg_time,
        'training_count': training_count,
        'reclassifications': reclassifications
    }
    
    # Get recent reclassifications
    c.execute('''SELECT timestamp, user_email, subject, old_category, new_category 
                 FROM reclassifications 
                 ORDER BY timestamp DESC 
                 LIMIT 20''')
    
    recent_reclassifications = []
    for row in c.fetchall():
        recent_reclassifications.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2] or 'No subject',
            'old_category': row[3],
            'new_category': row[4]
        })
    
    # Get recent classifications
    c.execute('''SELECT timestamp, user_email, subject, predicted_category, 
                        confidence, processing_time 
                 FROM classifications 
                 ORDER BY timestamp DESC 
                 LIMIT 50''')
    
    recent = []
    for row in c.fetchall():
        recent.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2] or 'No subject',
            'predicted_category': row[3],
            'confidence': row[4],
            'processing_time': row[5]
        })
    
    # Get training data distribution by user
    c.execute('''SELECT user_email,
                        SUM(CASE WHEN category = 'personal' THEN 1 ELSE 0 END) as personal,
                        SUM(CASE WHEN category = 'shopping' THEN 1 ELSE 0 END) as shopping,
                        SUM(CASE WHEN category = 'spam' THEN 1 ELSE 0 END) as spam,
                        COUNT(*) as total
                 FROM training_data
                 GROUP BY user_email''')
    
    training_dist = []
    for row in c.fetchall():
        training_dist.append({
            'user': row[0],
            'personal': row[1],
            'shopping': row[2],
            'spam': row[3],
            'total': row[4]
        })
    
    conn.close()

    # Get model stats
    model_stats = config.get_latest_model_stats()

    return render_template_string(TEMPLATE, stats=stats, recent=recent,
                                 training_dist=training_dist,
                                 recent_reclassifications=recent_reclassifications,
                                 model_stats=model_stats)

@app.route('/api/stats')
def api_stats():
    """API endpoint for stats"""
    conn = config.get_db()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM classifications')
    total = c.fetchone()[0]
    
    c.execute('SELECT AVG(processing_time) FROM classifications')
    avg_time = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(*) FROM reclassifications')
    reclassifications = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total': total,
        'avg_time': avg_time,
        'reclassifications': reclassifications
    })

@app.route('/api/reclassifications')
def api_reclassifications():
    """API endpoint for recent reclassifications"""
    limit = request.args.get('limit', 50, type=int)
    
    conn = config.get_db()
    c = conn.cursor()
    
    c.execute('''SELECT timestamp, user_email, subject, old_category, new_category 
                 FROM reclassifications 
                 ORDER BY timestamp DESC 
                 LIMIT ?''', (limit,))
    
    reclassifications = []
    for row in c.fetchall():
        reclassifications.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2],
            'old_category': row[3],
            'new_category': row[4]
        })
    
    conn.close()
    
    return jsonify(reclassifications)

@app.route('/api/refresh-imap', methods=['POST'])
def api_refresh_imap():
    """API endpoint to trigger IMAP refresh"""
    if _trainer is None:
        return jsonify({'success': False, 'error': 'Trainer not initialized'}), 500

    def refresh_worker():
        print("\n=== Manual IMAP Refresh Triggered ===")
        _trainer.check_reclassifications()
        print("=== IMAP Refresh Complete ===\n")

    # Run in background thread
    thread = threading.Thread(target=refresh_worker, daemon=True)
    thread.start()

    return jsonify({'success': True, 'message': 'IMAP refresh started'})

@app.route('/api/retrain', methods=['POST'])
def api_retrain():
    """API endpoint to trigger model retraining"""
    if _trainer is None:
        return jsonify({'success': False, 'error': 'Trainer not initialized'}), 500

    def retrain_worker():
        print("\n=== Manual Model Retrain Triggered ===")
        success = _trainer.retrain()
        if success:
            print("=== Model Retrain Complete ===\n")
        else:
            print("=== Model Retrain Failed ===\n")

    # Run in background thread
    thread = threading.Thread(target=retrain_worker, daemon=True)
    thread.start()

    return jsonify({'success': True, 'message': 'Model retraining started'})

@app.route('/api/model-stats')
def api_model_stats():
    """API endpoint for model statistics"""
    stats = config.get_latest_model_stats()
    if stats:
        return jsonify(stats)
    return jsonify({'error': 'No model stats available'}), 404

def run_web_ui(trainer=None, classifier=None):
    """Start the web UI with production WSGI server"""
    global _trainer, _classifier
    _trainer = trainer
    _classifier = classifier

    from waitress import serve
    print("Starting web dashboard on http://0.0.0.0:8080")
    serve(app, host='0.0.0.0', port=8080, threads=4)
