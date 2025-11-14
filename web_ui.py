from flask import Flask, render_template_string, jsonify, request
import config
from datetime import datetime, timedelta

app = Flask(__name__)

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
            background: #607D8B;
            color: white;
        }
        /* Default category colors */
        .personal { background: #2196F3; }
        .shopping { background: #FF9800; }
        .spam { background: #F44336; }
        .work { background: #9C27B0; }
        .finance { background: #4CAF50; }
        .social { background: #00BCD4; }
        .newsletters { background: #795548; }
        .receipts { background: #8BC34A; }
        .important { background: #E91E63; }
        .junk { background: #F44336; }
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
        }
        .refresh:hover {
            background: #45a049;
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
    </script>
</head>
<body>
    <div class="container">
        <h1>📧 Email Classifier Dashboard</h1>
        
        <button class="refresh" onclick="refresh()">Refresh Now</button>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Total Processed</div>
                <div class="stat-value">{{ stats.total }}</div>
            </div>
            {% for category in stats.all_categories %}
            <div class="stat-card">
                <div class="stat-label">{{ category|title }}</div>
                <div class="stat-value">{{ stats.category_counts.get(category, 0) }}</div>
            </div>
            {% endfor %}
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
                    {% for category in stats.all_categories %}
                    <th>{{ category|title }}</th>
                    {% endfor %}
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                {% for user_dist in training_dist %}
                <tr>
                    <td>{{ user_dist.user }}</td>
                    {% for category in stats.all_categories %}
                    <td>{{ user_dist.categories.get(category, 0) }}</td>
                    {% endfor %}
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

    # Get all categories and their counts dynamically
    c.execute('''SELECT predicted_category, COUNT(*)
                 FROM classifications
                 GROUP BY predicted_category''')
    category_counts = {row[0]: row[1] for row in c.fetchall()}

    c.execute('SELECT AVG(processing_time) FROM classifications')
    avg_time = c.fetchone()[0] or 0

    c.execute('SELECT COUNT(*) FROM training_data')
    training_count = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM reclassifications')
    reclassifications = c.fetchone()[0]

    # Get all known categories from folder_mappings
    all_categories = config.get_all_categories()

    stats = {
        'total': total,
        'category_counts': category_counts,
        'all_categories': all_categories,
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
    
    # Get training data distribution by user and category
    c.execute('''SELECT user_email, category, COUNT(*)
                 FROM training_data
                 GROUP BY user_email, category
                 ORDER BY user_email, category''')

    # Organize training distribution by user
    training_dist_data = {}
    for row in c.fetchall():
        user = row[0]
        category = row[1]
        count = row[2]

        if user not in training_dist_data:
            training_dist_data[user] = {'user': user, 'categories': {}, 'total': 0}

        training_dist_data[user]['categories'][category] = count
        training_dist_data[user]['total'] += count

    training_dist = list(training_dist_data.values())
    
    conn.close()
    
    return render_template_string(TEMPLATE, stats=stats, recent=recent, 
                                 training_dist=training_dist,
                                 recent_reclassifications=recent_reclassifications)

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

def run_web_ui():
    """Start the web UI with production WSGI server"""
    from waitress import serve
    print("Starting web dashboard on http://0.0.0.0:8080")
    serve(app, host='0.0.0.0', port=8080, threads=4)
