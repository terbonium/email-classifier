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
        /* Modal styles */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.show {
            display: flex;
        }
        .modal {
            background: white;
            border-radius: 8px;
            max-width: 800px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }
        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h3 {
            margin: 0;
            color: #333;
        }
        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #666;
            padding: 0;
            line-height: 1;
        }
        .modal-close:hover {
            color: #333;
        }
        .modal-body {
            padding: 20px;
        }
        .detail-section {
            margin-bottom: 20px;
        }
        .detail-section h4 {
            margin: 0 0 10px 0;
            color: #555;
            font-size: 14px;
            text-transform: uppercase;
        }
        .detail-content {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            font-size: 14px;
        }
        .prob-bar-container {
            margin: 8px 0;
        }
        .prob-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
            font-size: 13px;
        }
        .prob-bar {
            height: 20px;
            background: #e0e0e0;
            border-radius: 3px;
            overflow: hidden;
        }
        .prob-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s ease;
        }
        .prob-fill.personal { background: #2196F3; }
        .prob-fill.shopping { background: #FF9800; }
        .prob-fill.spam { background: #F44336; }
        .prob-fill.winner { box-shadow: 0 0 0 2px #333; }
        .explanation-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .explanation-list li {
            padding: 8px 0;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }
        .explanation-list li:last-child {
            border-bottom: none;
        }
        .clickable-row {
            cursor: pointer;
        }
        .clickable-row:hover {
            background: #e3f2fd !important;
        }
        .body-preview {
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
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

        function filterTrainingCategory(category) {
            const url = new URL(window.location);
            if (category) {
                url.searchParams.set('training_category', category);
            } else {
                url.searchParams.delete('training_category');
            }
            // Reset to page 1 when changing filter
            url.searchParams.delete('training_page');
            // Stay on training history tab
            url.searchParams.set('tab', 'training-history');
            window.location.href = url.toString();
        }

        // Restore active tab from URL on page load
        document.addEventListener('DOMContentLoaded', function() {
            const url = new URL(window.location);
            const tab = url.searchParams.get('tab') || 'overview';
            switchTab(tab);
        });

        // Modal functions
        function openClassificationModal(classificationId) {
            const modal = document.getElementById('classification-modal');
            const modalBody = document.getElementById('modal-body-content');

            // Show modal with loading state
            modal.classList.add('show');
            modalBody.innerHTML = '<div class="loading">Loading classification details...</div>';

            // Fetch classification details
            fetch(`/api/classification/${classificationId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        modalBody.innerHTML = `<div class="loading">Error: ${data.error}</div>`;
                        return;
                    }

                    // Build modal content
                    let html = '';

                    // Email header section
                    html += `
                        <div class="detail-section">
                            <h4>Email Details</h4>
                            <div class="detail-content">
                                <p><strong>Subject:</strong> ${escapeHtml(data.subject)}</p>
                                <p><strong>User:</strong> ${escapeHtml(data.user_email)}</p>
                                <p><strong>Timestamp:</strong> ${data.timestamp}</p>
                                <p><strong>Message ID:</strong> ${escapeHtml(data.message_id || 'N/A')}</p>
                                ${data.sender_domain ? `<p><strong>Sender Domain:</strong> ${escapeHtml(data.sender_domain)}</p>` : ''}
                            </div>
                        </div>
                    `;

                    // Classification result
                    html += `
                        <div class="detail-section">
                            <h4>Classification Result</h4>
                            <div class="detail-content">
                                <p><strong>Category:</strong> <span class="category ${data.predicted_category}">${data.predicted_category}</span></p>
                                <p><strong>Confidence:</strong> ${(data.confidence * 100).toFixed(1)}%</p>
                                <p><strong>Processing Time:</strong> ${data.processing_time.toFixed(3)}s</p>
                            </div>
                        </div>
                    `;

                    // Probability breakdown
                    if (data.probabilities) {
                        html += `
                            <div class="detail-section">
                                <h4>Probability Breakdown</h4>
                                <div class="detail-content">
                        `;

                        const categories = ['personal', 'shopping', 'spam'];
                        categories.forEach(cat => {
                            const prob = data.probabilities[cat] || 0;
                            const isWinner = cat === data.predicted_category;
                            html += `
                                <div class="prob-bar-container">
                                    <div class="prob-label">
                                        <span>${cat.charAt(0).toUpperCase() + cat.slice(1)}</span>
                                        <span>${(prob * 100).toFixed(1)}%</span>
                                    </div>
                                    <div class="prob-bar">
                                        <div class="prob-fill ${cat} ${isWinner ? 'winner' : ''}" style="width: ${prob * 100}%"></div>
                                    </div>
                                </div>
                            `;
                        });

                        html += `
                                </div>
                            </div>
                        `;
                    }

                    // Explanation
                    if (data.explanation && data.explanation.length > 0) {
                        html += `
                            <div class="detail-section">
                                <h4>Why This Classification?</h4>
                                <div class="detail-content">
                                    <ul class="explanation-list">
                        `;

                        data.explanation.forEach(item => {
                            html += `<li>${escapeHtml(item)}</li>`;
                        });

                        html += `
                                    </ul>
                                </div>
                            </div>
                        `;
                    }

                    // Body preview
                    if (data.body_preview) {
                        html += `
                            <div class="detail-section">
                                <h4>Email Body Preview</h4>
                                <div class="detail-content">
                                    <div class="body-preview">${escapeHtml(data.body_preview)}</div>
                                </div>
                            </div>
                        `;
                    } else {
                        html += `
                            <div class="detail-section">
                                <h4>Email Body</h4>
                                <div class="detail-content">
                                    <p style="color: #666; font-style: italic;">Body content not available for this email.</p>
                                </div>
                            </div>
                        `;
                    }

                    modalBody.innerHTML = html;
                })
                .catch(error => {
                    modalBody.innerHTML = `<div class="loading">Error loading details: ${error.message}</div>`;
                });
        }

        function closeModal() {
            const modal = document.getElementById('classification-modal');
            modal.classList.remove('show');
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Close modal on overlay click
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('modal-overlay')) {
                closeModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeModal();
            }
        });
    </script>
</head>
<body>
    <div id="toast" class="toast"></div>

    <!-- Classification Details Modal -->
    <div id="classification-modal" class="modal-overlay">
        <div class="modal">
            <div class="modal-header">
                <h3>Classification Details</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body-content">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>

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
        <p style="color: #666; font-size: 14px;">Click on a row to view classification details and explanation.</p>
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
                <tr class="clickable-row" onclick="openClassificationModal({{ record.id }})">
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
                Complete history of emails classified for {{ selected_user }}.
                {% else %}
                Complete history of all classified emails. Select a user to filter.
                {% endif %}
                Click on a row to view classification details and explanation.
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
                    <tr class="clickable-row" onclick="openClassificationModal({{ record.id }})">
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

            <div style="margin: 15px 0; display: flex; align-items: center; gap: 10px;">
                <label for="training-category-filter" style="font-weight: bold;">Filter by category:</label>
                <select id="training-category-filter" onchange="filterTrainingCategory(this.value)" style="padding: 8px; border-radius: 4px; border: 1px solid #ddd;">
                    <option value="" {% if not training_category %}selected{% endif %}>All Categories</option>
                    <option value="personal" {% if training_category == 'personal' %}selected{% endif %}>Personal</option>
                    <option value="shopping" {% if training_category == 'shopping' %}selected{% endif %}>Shopping</option>
                    <option value="spam" {% if training_category == 'spam' %}selected{% endif %}>Spam</option>
                </select>
            </div>

            <h3 style="margin-top: 20px;">Training Data (Emails in Training Folders) - {{ training_total }}{% if training_category %} {{ training_category }}{% endif %} total</h3>
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
                <button onclick="window.location.href='?tab=training-history&training_page={{ training_page - 1 }}{% if selected_user %}&user={{ selected_user }}{% endif %}{% if training_category %}&training_category={{ training_category }}{% endif %}'">Previous</button>
                {% else %}
                <button disabled>Previous</button>
                {% endif %}
                <span style="margin: 0 15px;">Page {{ training_page }} of {{ training_total_pages }}</span>
                {% if training_page < training_total_pages %}
                <button onclick="window.location.href='?tab=training-history&training_page={{ training_page + 1 }}{% if selected_user %}&user={{ selected_user }}{% endif %}{% if training_category %}&training_category={{ training_category }}{% endif %}'">Next</button>
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

    # Pagination and filtering for training history
    training_page = request.args.get('training_page', 1, type=int)
    training_per_page = 100
    training_offset = (training_page - 1) * training_per_page
    training_category = request.args.get('training_category', '')

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
        c.execute('''SELECT id, timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 50''', (selected_user,))
    else:
        c.execute('''SELECT id, timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     ORDER BY timestamp DESC
                     LIMIT 50''')

    recent = []
    for row in c.fetchall():
        recent.append({
            'id': row[0],
            'timestamp': row[1],
            'user_email': row[2],
            'subject': row[3] or 'No subject',
            'predicted_category': row[4],
            'confidence': row[5],
            'processing_time': row[6]
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
        c.execute('''SELECT id, timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     WHERE user_email = ?
                     ORDER BY timestamp DESC
                     LIMIT 200''', (selected_user,))
    else:
        c.execute('''SELECT id, timestamp, user_email, subject, predicted_category,
                            confidence, processing_time
                     FROM classifications
                     ORDER BY timestamp DESC
                     LIMIT 200''')

    mail_history = []
    for row in c.fetchall():
        mail_history.append({
            'id': row[0],
            'timestamp': row[1],
            'user_email': row[2],
            'subject': row[3] or 'No subject',
            'predicted_category': row[4],
            'confidence': row[5],
            'processing_time': row[6]
        })

    # Get training history (for training history tab) with pagination and filtering
    # Build WHERE clause for training history
    training_conditions = []
    training_params = []
    if selected_user:
        training_conditions.append('user_email = ?')
        training_params.append(selected_user)
    if training_category:
        training_conditions.append('category = ?')
        training_params.append(training_category)

    training_where = ''
    if training_conditions:
        training_where = ' WHERE ' + ' AND '.join(training_conditions)

    # Get count for pagination
    c.execute(f'SELECT COUNT(*) FROM training_data{training_where}', training_params)
    training_total = c.fetchone()[0]

    # Get paginated results
    c.execute(f'''SELECT timestamp, user_email, subject, category
                 FROM training_data{training_where}
                 ORDER BY timestamp DESC
                 LIMIT ? OFFSET ?''', training_params + [training_per_page, training_offset])

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
                                 training_total=training_total,
                                 training_category=training_category)

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

@app.route('/api/classification/<int:classification_id>')
def api_classification_details(classification_id):
    """API endpoint for detailed classification with explainability"""
    conn = config.get_db()
    c = conn.cursor()

    # Get classification with all probability data
    c.execute('''SELECT c.id, c.message_id, c.user_email, c.subject, c.predicted_category,
                        c.confidence, c.processing_time, c.timestamp,
                        c.personal_prob, c.shopping_prob, c.spam_prob, c.sender_domain,
                        t.body
                 FROM classifications c
                 LEFT JOIN training_data t ON c.message_id = t.message_id AND c.user_email = t.user_email
                 WHERE c.id = ?''', (classification_id,))

    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Classification not found'}), 404

    # Build probability breakdown
    probabilities = {}
    has_probabilities = row[8] is not None  # personal_prob

    if has_probabilities:
        probabilities = {
            'personal': row[8],
            'shopping': row[9],
            'spam': row[10]
        }
    else:
        # For older classifications without probability data
        probabilities = None

    # Generate explanation
    explanation = generate_classification_explanation(
        predicted_category=row[4],
        confidence=row[5],
        probabilities=probabilities,
        sender_domain=row[11]
    )

    # Format body preview (first 1000 chars)
    body = row[12] or ''
    body_preview = body[:1000] + ('...' if len(body) > 1000 else '')

    return jsonify({
        'id': row[0],
        'message_id': row[1],
        'user_email': row[2],
        'subject': row[3],
        'predicted_category': row[4],
        'confidence': row[5],
        'processing_time': row[6],
        'timestamp': row[7],
        'probabilities': probabilities,
        'sender_domain': row[11],
        'body_preview': body_preview,
        'explanation': explanation
    })

def generate_classification_explanation(predicted_category, confidence, probabilities, sender_domain):
    """Generate a human-readable explanation of the classification decision"""
    explanation = []

    if not probabilities:
        explanation.append("Detailed probability data is not available for this classification (older record).")
        explanation.append(f"The email was classified as '{predicted_category}' with {confidence*100:.1f}% confidence.")
        return explanation

    # Sort probabilities for comparison
    sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
    winner = sorted_probs[0]
    runner_up = sorted_probs[1] if len(sorted_probs) > 1 else None

    # Primary classification reason
    explanation.append(f"Classified as '{predicted_category}' with {confidence*100:.1f}% confidence.")

    # Probability breakdown
    prob_text = "Probability breakdown: " + ", ".join([f"{cat}: {prob*100:.1f}%" for cat, prob in sorted_probs])
    explanation.append(prob_text)

    # Confidence level interpretation
    if confidence > 0.9:
        explanation.append("Very high confidence - the model is highly certain about this classification.")
    elif confidence > 0.7:
        explanation.append("Good confidence - the model is reasonably certain about this classification.")
    elif confidence > 0.5:
        explanation.append("Moderate confidence - the classification is likely correct but has some uncertainty.")
    else:
        explanation.append("Low confidence - the model is uncertain about this classification.")

    # Compare with runner-up
    if runner_up:
        margin = winner[1] - runner_up[1]
        if margin < 0.1:
            explanation.append(f"Close decision: '{runner_up[0]}' was a close second ({runner_up[1]*100:.1f}%).")
        elif margin < 0.3:
            explanation.append(f"'{runner_up[0]}' was considered but had lower probability ({runner_up[1]*100:.1f}%).")

    # Sender domain heuristics
    if sender_domain:
        civic_domains = ['.gov', '.edu', '.org']
        civic_keywords = ['government', 'county', 'city', 'state', 'municipal', 'district', 'commissioner']

        is_civic = any(sender_domain.endswith(d) for d in civic_domains) or \
                   any(kw in sender_domain for kw in civic_keywords)

        if is_civic:
            explanation.append(f"Sender domain '{sender_domain}' is a civic/institutional domain - shopping probability was reduced.")

    return explanation

def run_web_ui(trainer=None, classifier=None):
    """Start the web UI with production WSGI server"""
    global _trainer, _classifier
    _trainer = trainer
    _classifier = classifier

    from waitress import serve
    print("Starting web dashboard on http://0.0.0.0:8080")
    serve(app, host='0.0.0.0', port=8080, threads=4)
