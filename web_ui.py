from flask import Flask, render_template_string, jsonify, request
import config
from datetime import datetime, timedelta
import threading

app = Flask(__name__)

# Global references to trainer and classifier (set by run_web_ui)
_trainer = None
_classifier = None

def get_all_users():
    """Get list of all users from database"""
    conn = config.get_db()
    c = conn.cursor()

    # Get users from classifications
    c.execute('SELECT DISTINCT user_email FROM classifications WHERE user_email IS NOT NULL')
    users = set(row[0] for row in c.fetchall())

    # Also get users from training data
    c.execute('SELECT DISTINCT user_email FROM training_data WHERE user_email IS NOT NULL')
    users.update(row[0] for row in c.fetchall())

    # Also get users from reclassifications
    c.execute('SELECT DISTINCT user_email FROM reclassifications WHERE user_email IS NOT NULL')
    users.update(row[0] for row in c.fetchall())

    conn.close()
    return sorted(list(users))

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
        .user-selector {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .user-selector label {
            font-weight: bold;
            color: #1565c0;
        }
        .user-selector select {
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #90caf9;
            font-size: 14px;
            min-width: 250px;
        }
        .user-info {
            margin-left: auto;
            color: #666;
            font-size: 14px;
        }
        .tabs {
            display: flex;
            border-bottom: 2px solid #ddd;
            margin: 20px 0 0 0;
        }
        .tab {
            padding: 12px 24px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 14px;
            font-weight: bold;
            color: #666;
            border-bottom: 3px solid transparent;
            margin-bottom: -2px;
        }
        .tab:hover {
            color: #4CAF50;
        }
        .tab.active {
            color: #4CAF50;
            border-bottom-color: #4CAF50;
        }
        .tab-content {
            display: none;
            padding: 20px 0;
        }
        .tab-content.active {
            display: block;
        }
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .section-header h2 {
            margin: 0;
        }
        .pagination {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .pagination button {
            padding: 6px 12px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 4px;
            cursor: pointer;
        }
        .pagination button:hover {
            background: #f5f5f5;
        }
        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #666;
            background: #f9f9f9;
            border-radius: 8px;
        }
        .training-category {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
        }
    </style>
    <script>
        function refresh() {
            location.reload();
        }
        // Auto-refresh more frequently if training is in progress
        {% if training_status and training_status.is_training %}
        setInterval(refresh, 10000); // Refresh every 10 seconds during training
        {% else %}
        setInterval(refresh, 30000); // Refresh every 30 seconds normally
        {% endif %}

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

        function changeUser() {
            const selector = document.getElementById('user-select');
            const selectedUser = selector.value;
            const url = new URL(window.location);
            if (selectedUser) {
                url.searchParams.set('user', selectedUser);
            } else {
                url.searchParams.delete('user');
            }
            window.location.href = url.toString();
        }

        function switchTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`tab-${tabName}`).classList.add('active');

            // Store active tab in URL
            const url = new URL(window.location);
            url.searchParams.set('tab', tabName);
            history.replaceState(null, '', url.toString());
        }

        // Restore active tab from URL on page load
        document.addEventListener('DOMContentLoaded', function() {
            const url = new URL(window.location);
            const tab = url.searchParams.get('tab') || 'overview';
            switchTab(tab);
        });
    </script>
</head>
<body>
    <div id="toast" class="toast"></div>
    <div class="container">
        <h1>Email Classifier Dashboard</h1>

        <div class="user-selector">
            <label for="user-select">View Account:</label>
            <select id="user-select" onchange="changeUser()">
                <option value="">All Users (Aggregate)</option>
                {% for user in users %}
                <option value="{{ user }}" {% if selected_user == user %}selected{% endif %}>{{ user }}</option>
                {% endfor %}
            </select>
            {% if selected_user %}
            <span class="user-info">Showing data for: <strong>{{ selected_user }}</strong></span>
            {% else %}
            <span class="user-info">Showing aggregate data for all users</span>
            {% endif %}
        </div>

        <div class="button-group">
            <button class="refresh" onclick="refresh()">Refresh Dashboard</button>
            <button id="btn-refresh-imap" class="btn-action" onclick="refreshIMAP()">Check for Reclassified Emails</button>
            <button id="btn-retrain" class="btn-action btn-warning" onclick="retrainModel()">Retrain Model</button>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="overview" onclick="switchTab('overview')">Overview</button>
            <button class="tab" data-tab="mail-history" onclick="switchTab('mail-history')">Mail History</button>
            <button class="tab" data-tab="training-history" onclick="switchTab('training-history')">Training History</button>
        </div>

        <!-- Overview Tab -->
        <div id="tab-overview" class="tab-content active">

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

        {% if training_status and training_status.is_training %}
        <div class="model-stats-card">
            <h3 style="margin-top: 0; color: #FF9800;">🔄 Training in Progress</h3>
            <p style="color: #FF9800; font-size: 16px; margin: 10px 0;">
                <strong>Model training is currently in progress...</strong>
            </p>
            <div style="background: #FFF3E0; padding: 15px; border-radius: 4px; margin-top: 10px;">
                <div style="margin-bottom: 8px;">
                    <strong>Training Samples:</strong> {{ training_status.num_samples }}
                </div>
                <div style="margin-bottom: 8px;">
                    <strong>Started:</strong> {{ training_status.started_at }}
                </div>
                <div style="color: #666; font-size: 14px; margin-top: 12px;">
                    Please wait... This may take a few minutes depending on the dataset size. The page will automatically refresh to show the results when training completes.
                </div>
            </div>
        </div>
        {% elif model_stats %}
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

        </div><!-- End Overview Tab -->

        <!-- Mail History Tab -->
        <div id="tab-mail-history" class="tab-content">
            <div class="section-header">
                <h2>Mail Classification History</h2>
            </div>
            <p style="color: #666; font-size: 14px;">
                {% if selected_user %}
                Complete history of emails classified for {{ selected_user }}
                {% else %}
                Complete history of all classified emails. Select a user to filter.
                {% endif %}
            </p>

            {% if mail_history %}
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        {% if not selected_user %}<th>User</th>{% endif %}
                        <th>Subject</th>
                        <th>Category</th>
                        <th>Confidence</th>
                        <th>Time (s)</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in mail_history %}
                    <tr>
                        <td>{{ record.timestamp }}</td>
                        {% if not selected_user %}<td>{{ record.user_email }}</td>{% endif %}
                        <td>{{ record.subject[:80] }}{% if record.subject|length > 80 %}...{% endif %}</td>
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
            {% else %}
            <div class="empty-state">
                <p>No mail history available{% if selected_user %} for {{ selected_user }}{% endif %}.</p>
            </div>
            {% endif %}
        </div><!-- End Mail History Tab -->

        <!-- Training History Tab -->
        <div id="tab-training-history" class="tab-content">
            <div class="section-header">
                <h2>Training Classification History</h2>
            </div>
            <p style="color: #666; font-size: 14px;">
                {% if selected_user %}
                Training data and reclassifications for {{ selected_user }}. This data is used to train the model.
                {% else %}
                All training data across users. Select a user to see their specific training history.
                {% endif %}
            </p>

            <h3 style="margin-top: 20px;">Training Data (Emails in Training Folders) - {{ training_total }} total</h3>
            {% if training_history %}
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        {% if not selected_user %}<th>User</th>{% endif %}
                        <th>Subject</th>
                        <th>Category</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in training_history %}
                    <tr>
                        <td>{{ record.timestamp }}</td>
                        {% if not selected_user %}<td>{{ record.user_email }}</td>{% endif %}
                        <td>{{ record.subject[:80] }}{% if record.subject|length > 80 %}...{% endif %}</td>
                        <td><span class="category {{ record.category }}">{{ record.category }}</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                <p>No training data available{% if selected_user %} for {{ selected_user }}{% endif %}.</p>
            </div>
            {% endif %}

            {% if training_total_pages > 1 %}
            <div class="pagination" style="margin-top: 15px;">
                {% if training_page > 1 %}
                <button onclick="window.location.href='?tab=training-history&training_page={{ training_page - 1 }}{% if selected_user %}&user={{ selected_user }}{% endif %}'">Previous</button>
                {% else %}
                <button disabled>Previous</button>
                {% endif %}
                <span style="margin: 0 15px;">Page {{ training_page }} of {{ training_total_pages }}</span>
                {% if training_page < training_total_pages %}
                <button onclick="window.location.href='?tab=training-history&training_page={{ training_page + 1 }}{% if selected_user %}&user={{ selected_user }}{% endif %}'">Next</button>
                {% else %}
                <button disabled>Next</button>
                {% endif %}
            </div>
            {% endif %}

            <h3 style="margin-top: 30px;">Reclassification History (User Corrections)</h3>
            <p style="color: #666; font-size: 14px;">When you move emails between folders, the system learns from these corrections.</p>
            {% if user_reclassifications %}
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        {% if not selected_user %}<th>User</th>{% endif %}
                        <th>Subject</th>
                        <th>Movement</th>
                    </tr>
                </thead>
                <tbody>
                    {% for reclass in user_reclassifications %}
                    <tr>
                        <td>{{ reclass.timestamp }}</td>
                        {% if not selected_user %}<td>{{ reclass.user_email }}</td>{% endif %}
                        <td>{{ reclass.subject[:60] }}{% if reclass.subject|length > 60 %}...{% endif %}</td>
                        <td>
                            <div class="reclassification">
                                <span class="category {{ reclass.old_category }}">{{ reclass.old_category }}</span>
                                <span class="arrow">-></span>
                                <span class="category {{ reclass.new_category }}">{{ reclass.new_category }}</span>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                <p>No reclassifications recorded{% if selected_user %} for {{ selected_user }}{% endif %}.</p>
            </div>
            {% endif %}
        </div><!-- End Training History Tab -->

    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard with user filtering support"""
    conn = config.get_db()
    c = conn.cursor()

    # Get selected user from query params
    selected_user = request.args.get('user', '')
    users = get_all_users()

    # Pagination for training history
    training_page = request.args.get('training_page', 1, type=int)
    training_per_page = 100
    training_offset = (training_page - 1) * training_per_page

    # Build WHERE clause for user filtering
    user_filter = ''
    user_params = ()
    if selected_user:
        user_filter = ' WHERE user_email = ?'
        user_params = (selected_user,)

    # Get overall stats (filtered by user if selected)
    c.execute(f'SELECT COUNT(*) FROM classifications{user_filter}', user_params)
    total = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM classifications{user_filter}{' AND' if user_filter else ' WHERE'} predicted_category = 'personal'",
              user_params)
    personal = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM classifications{user_filter}{' AND' if user_filter else ' WHERE'} predicted_category = 'shopping'",
              user_params)
    shopping = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM classifications{user_filter}{' AND' if user_filter else ' WHERE'} predicted_category = 'spam'",
              user_params)
    spam = c.fetchone()[0]

    c.execute(f'SELECT AVG(processing_time) FROM classifications{user_filter}', user_params)
    avg_time = c.fetchone()[0] or 0

    c.execute(f'SELECT COUNT(*) FROM training_data{user_filter}', user_params)
    training_count = c.fetchone()[0]

    c.execute(f'SELECT COUNT(*) FROM reclassifications{user_filter}', user_params)
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

    # Get recent reclassifications (for overview tab)
    if selected_user:
        c.execute('''SELECT timestamp, user_email, subject, old_category, new_category
                     FROM reclassifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 20''', (selected_user,))
    else:
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

    # Get recent classifications (for overview tab)
    if selected_user:
        c.execute('''SELECT timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 50''', (selected_user,))
    else:
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
    if selected_user:
        c.execute('''SELECT user_email,
                            SUM(CASE WHEN category = 'personal' THEN 1 ELSE 0 END) as personal,
                            SUM(CASE WHEN category = 'shopping' THEN 1 ELSE 0 END) as shopping,
                            SUM(CASE WHEN category = 'spam' THEN 1 ELSE 0 END) as spam,
                            COUNT(*) as total
                     FROM training_data
                     WHERE user_email = ?
                     GROUP BY user_email''', (selected_user,))
    else:
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

    # Get mail history (for mail history tab) - more records
    if selected_user:
        c.execute('''SELECT timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 200''', (selected_user,))
    else:
        c.execute('''SELECT timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     ORDER BY timestamp DESC
                     LIMIT 200''')

    mail_history = []
    for row in c.fetchall():
        mail_history.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2] or 'No subject',
            'predicted_category': row[3],
            'confidence': row[4],
            'processing_time': row[5]
        })

    # Get training history (for training history tab) with pagination
    if selected_user:
        c.execute('SELECT COUNT(*) FROM training_data WHERE user_email = ?', (selected_user,))
        training_total = c.fetchone()[0]
        c.execute('''SELECT timestamp, user_email, subject, category
                     FROM training_data
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT ? OFFSET ?''', (selected_user, training_per_page, training_offset))
    else:
        c.execute('SELECT COUNT(*) FROM training_data')
        training_total = c.fetchone()[0]
        c.execute('''SELECT timestamp, user_email, subject, category
                     FROM training_data
                     ORDER BY timestamp DESC
                     LIMIT ? OFFSET ?''', (training_per_page, training_offset))

    training_total_pages = (training_total + training_per_page - 1) // training_per_page
    training_history = []
    for row in c.fetchall():
        training_history.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2] or 'No subject',
            'category': row[3]
        })

    # Get user reclassifications (for training history tab)
    if selected_user:
        c.execute('''SELECT timestamp, user_email, subject, old_category, new_category
                     FROM reclassifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 100''', (selected_user,))
    else:
        c.execute('''SELECT timestamp, user_email, subject, old_category, new_category
                     FROM reclassifications
                     ORDER BY timestamp DESC
                     LIMIT 100''')

    user_reclassifications = []
    for row in c.fetchall():
        user_reclassifications.append({
            'timestamp': row[0],
            'user_email': row[1],
            'subject': row[2] or 'No subject',
            'old_category': row[3],
            'new_category': row[4]
        })

    conn.close()

    # Get model stats and training status
    model_stats = config.get_latest_model_stats()
    training_status = config.get_training_status()

    return render_template_string(TEMPLATE,
                                 stats=stats,
                                 recent=recent,
                                 training_dist=training_dist,
                                 recent_reclassifications=recent_reclassifications,
                                 model_stats=model_stats,
                                 training_status=training_status,
                                 users=users,
                                 selected_user=selected_user,
                                 mail_history=mail_history,
                                 training_history=training_history,
                                 user_reclassifications=user_reclassifications,
                                 training_page=training_page,
                                 training_total_pages=training_total_pages,
                                 training_total=training_total)

@app.route('/api/users')
def api_users():
    """API endpoint to get list of all users"""
    users = get_all_users()
    return jsonify({'users': users})

@app.route('/api/stats')
def api_stats():
    """API endpoint for stats (supports user filtering)"""
    user_email = request.args.get('user', '')

    conn = config.get_db()
    c = conn.cursor()

    if user_email:
        c.execute('SELECT COUNT(*) FROM classifications WHERE user_email = ?', (user_email,))
        total = c.fetchone()[0]

        c.execute('SELECT AVG(processing_time) FROM classifications WHERE user_email = ?', (user_email,))
        avg_time = c.fetchone()[0] or 0

        c.execute('SELECT COUNT(*) FROM reclassifications WHERE user_email = ?', (user_email,))
        reclassifications = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM training_data WHERE user_email = ?', (user_email,))
        training_count = c.fetchone()[0]
    else:
        c.execute('SELECT COUNT(*) FROM classifications')
        total = c.fetchone()[0]

        c.execute('SELECT AVG(processing_time) FROM classifications')
        avg_time = c.fetchone()[0] or 0

        c.execute('SELECT COUNT(*) FROM reclassifications')
        reclassifications = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM training_data')
        training_count = c.fetchone()[0]

    conn.close()

    return jsonify({
        'total': total,
        'avg_time': avg_time,
        'reclassifications': reclassifications,
        'training_count': training_count,
        'user': user_email or 'all'
    })

@app.route('/api/user/<user_email>/mail-history')
def api_user_mail_history(user_email):
    """API endpoint for user-specific mail classification history"""
    limit = request.args.get('limit', 200, type=int)

    conn = config.get_db()
    c = conn.cursor()

    c.execute('''SELECT timestamp, subject, predicted_category, confidence, processing_time
                 FROM classifications
                 WHERE user_email = ?
                 ORDER BY timestamp DESC
                 LIMIT ?''', (user_email, limit))

    history = []
    for row in c.fetchall():
        history.append({
            'timestamp': row[0],
            'subject': row[1],
            'predicted_category': row[2],
            'confidence': row[3],
            'processing_time': row[4]
        })

    conn.close()

    return jsonify({'user': user_email, 'mail_history': history, 'count': len(history)})

@app.route('/api/user/<user_email>/training-history')
def api_user_training_history(user_email):
    """API endpoint for user-specific training data history"""
    limit = request.args.get('limit', 200, type=int)

    conn = config.get_db()
    c = conn.cursor()

    c.execute('''SELECT timestamp, subject, category
                 FROM training_data
                 WHERE user_email = ?
                 ORDER BY timestamp DESC
                 LIMIT ?''', (user_email, limit))

    training_data = []
    for row in c.fetchall():
        training_data.append({
            'timestamp': row[0],
            'subject': row[1],
            'category': row[2]
        })

    c.execute('''SELECT timestamp, subject, old_category, new_category
                 FROM reclassifications
                 WHERE user_email = ?
                 ORDER BY timestamp DESC
                 LIMIT ?''', (user_email, limit))

    reclassifications = []
    for row in c.fetchall():
        reclassifications.append({
            'timestamp': row[0],
            'subject': row[1],
            'old_category': row[2],
            'new_category': row[3]
        })

    conn.close()

    return jsonify({
        'user': user_email,
        'training_data': training_data,
        'reclassifications': reclassifications
    })

@app.route('/api/reclassifications')
def api_reclassifications():
    """API endpoint for recent reclassifications (supports user filtering)"""
    limit = request.args.get('limit', 50, type=int)
    user_email = request.args.get('user', '')

    conn = config.get_db()
    c = conn.cursor()

    if user_email:
        c.execute('''SELECT timestamp, user_email, subject, old_category, new_category
                     FROM reclassifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT ?''', (user_email, limit))
    else:
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
