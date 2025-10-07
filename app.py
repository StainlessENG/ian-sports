from flask import Flask, request, Response, jsonify, render_template_string
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time

app = Flask(__name__)

# --- CONFIG ---
M3U_URL = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"
EPG_URL = "http://websafety101.net:5050/xmltv.php?username=chulobonao7@aol.com&password=TQRfqAp9dA"
VALID_USERS = {"sid": "devon", "john": "pass123"}
MAX_CONNECTIONS_PER_USER = 2  # Max simultaneous streams per user
ADMIN_PASSWORD = "admin123"  # Password to access dashboard
# ----------------

# Global tracking
active_connections = {}  # {session_id: {user, ip, channel, start_time}}
connection_history = []  # List of past connections
user_stats = defaultdict(lambda: {"total_time": 0, "sessions": 0, "last_seen": None})
lock = threading.Lock()

def cleanup_dead_connections():
    """Remove stale connections (older than 5 minutes without activity)"""
    while True:
        time.sleep(60)  # Check every minute
        with lock:
            now = datetime.now()
            to_remove = []
            for session_id, conn in active_connections.items():
                if (now - conn['last_active']).seconds > 300:  # 5 minutes
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                end_session(session_id)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_dead_connections, daemon=True)
cleanup_thread.start()

def get_session_id():
    """Generate unique session ID from request"""
    return f"{request.args.get('username', 'unknown')}_{request.remote_addr}_{int(time.time())}"

def start_session(username, channel="Unknown"):
    """Record a new streaming session"""
    session_id = get_session_id()
    with lock:
        # Check connection limit
        user_connections = sum(1 for c in active_connections.values() if c['user'] == username)
        if user_connections >= MAX_CONNECTIONS_PER_USER:
            return None
        
        active_connections[session_id] = {
            'user': username,
            'ip': request.remote_addr,
            'channel': channel,
            'start_time': datetime.now(),
            'last_active': datetime.now()
        }
        user_stats[username]['sessions'] += 1
        user_stats[username]['last_seen'] = datetime.now()
    
    return session_id

def update_session(session_id):
    """Update last active time for a session"""
    with lock:
        if session_id in active_connections:
            active_connections[session_id]['last_active'] = datetime.now()

def end_session(session_id):
    """End a streaming session and record stats"""
    with lock:
        if session_id in active_connections:
            conn = active_connections[session_id]
            duration = (datetime.now() - conn['start_time']).seconds
            user_stats[conn['user']]['total_time'] += duration
            
            connection_history.append({
                'user': conn['user'],
                'ip': conn['ip'],
                'channel': conn['channel'],
                'start': conn['start_time'],
                'duration': duration
            })
            
            # Keep only last 100 history entries
            if len(connection_history) > 100:
                connection_history.pop(0)
            
            del active_connections[session_id]

def check_auth():
    """Check if username and password are valid"""
    username = request.args.get('username', '')
    password = request.args.get('password', '')
    
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return None
    return username

def check_admin_auth():
    """Check admin password"""
    password = request.args.get('password', '')
    return password == ADMIN_PASSWORD

@app.route('/get.php')
def get_php():
    username = check_auth()
    if not username:
        return Response("User not found or bad password", status=403)
    
    # Start tracking session
    session_id = start_session(username, "M3U Playlist")
    if session_id is None:
        return Response(f"Connection limit reached ({MAX_CONNECTIONS_PER_USER} max)", status=429)
    
    resp = requests.get(M3U_URL)
    if resp.status_code != 200:
        end_session(session_id)
        return Response("Could not fetch M3U", status=500)
    
    return Response(resp.content, mimetype='application/x-mpegURL')

@app.route('/xmltv.php')
def xmltv():
    username = check_auth()
    if not username:
        return Response("User not found or bad password", status=403)
    
    if not EPG_URL:
        return Response("EPG not configured", status=404)
    
    resp = requests.get(EPG_URL)
    if resp.status_code != 200:
        return Response("Could not fetch EPG", status=500)
    
    return Response(resp.content, mimetype='application/xml')

@app.route('/player_api.php')
def player_api():
    username = check_auth()
    if not username:
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})
    
    action = request.args.get('action', '')
    
    if action == 'get_live_categories':
        return jsonify([{"category_id": "1", "category_name": "Live TV", "parent_id": 0}])
    
    elif action == 'get_live_streams':
        return jsonify([])
    
    else:
        return jsonify({
            "user_info": {
                "username": username,
                "auth": 1,
                "status": "Active",
                "exp_date": "1999999999",
                "is_trial": "0",
                "active_cons": str(sum(1 for c in active_connections.values() if c['user'] == username)),
                "max_connections": str(MAX_CONNECTIONS_PER_USER)
            }
        })

@app.route('/admin/dashboard')
def admin_dashboard():
    if not check_admin_auth():
        return Response("Access denied. Use ?password=admin123", status=403)
    
    with lock:
        connections = list(active_connections.items())
        history = list(connection_history[-20:])  # Last 20
        stats = dict(user_stats)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Xtream Bridge Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #fff; }
            h1 { color: #4CAF50; }
            h2 { color: #2196F3; margin-top: 30px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; background: #2a2a2a; }
            th { background: #4CAF50; color: white; padding: 12px; text-align: left; }
            td { padding: 10px; border-bottom: 1px solid #444; }
            tr:hover { background: #333; }
            .stats { display: flex; gap: 20px; margin: 20px 0; }
            .stat-box { background: #2a2a2a; padding: 20px; border-radius: 8px; flex: 1; }
            .stat-value { font-size: 32px; font-weight: bold; color: #4CAF50; }
            .stat-label { color: #888; margin-top: 5px; }
            .kick-btn { background: #f44336; color: white; border: none; padding: 5px 10px; cursor: pointer; border-radius: 4px; }
            .kick-btn:hover { background: #d32f2f; }
            .online { color: #4CAF50; }
            .offline { color: #f44336; }
        </style>
    </head>
    <body>
        <h1>🎬 Xtream Bridge Dashboard</h1>
        <p>Auto-refreshes every 5 seconds | Current time: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">""" + str(len(connections)) + """</div>
                <div class="stat-label">Active Connections</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">""" + str(len(VALID_USERS)) + """</div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">""" + str(len(history)) + """</div>
                <div class="stat-label">Recent Sessions</div>
            </div>
        </div>
        
        <h2>🔴 Live Connections</h2>
        <table>
            <tr>
                <th>User</th>
                <th>Channel</th>
                <th>Duration</th>
                <th>IP Address</th>
                <th>Action</th>
            </tr>
    """
    
    if connections:
        for session_id, conn in connections:
            duration = datetime.now() - conn['start_time']
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            seconds = duration.seconds % 60
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            html += f"""
            <tr>
                <td><strong>{conn['user']}</strong></td>
                <td>{conn['channel']}</td>
                <td>{duration_str}</td>
                <td>{conn['ip']}</td>
                <td><button class="kick-btn" onclick="alert('Kick feature coming soon!')">KICK</button></td>
            </tr>
            """
    else:
        html += '<tr><td colspan="5" style="text-align: center; color: #888;">No active connections</td></tr>'
    
    html += """
        </table>
        
        <h2>📊 User Statistics</h2>
        <table>
            <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Total Time</th>
                <th>Sessions</th>
                <th>Last Seen</th>
            </tr>
    """
    
    for username in VALID_USERS:
        stat = stats.get(username, {"total_time": 0, "sessions": 0, "last_seen": None})
        is_online = any(c['user'] == username for _, c in connections)
        status = '<span class="online">● ONLINE</span>' if is_online else '<span class="offline">● OFFLINE</span>'
        
        hours = stat['total_time'] // 3600
        minutes = (stat['total_time'] % 3600) // 60
        time_str = f"{hours}h {minutes}m"
        
        last_seen = stat['last_seen'].strftime("%Y-%m-%d %H:%M") if stat['last_seen'] else "Never"
        
        html += f"""
        <tr>
            <td><strong>{username}</strong></td>
            <td>{status}</td>
            <td>{time_str}</td>
            <td>{stat['sessions']}</td>
            <td>{last_seen}</td>
        </tr>
        """
    
    html += """
        </table>
        
        <h2>📜 Recent Activity</h2>
        <table>
            <tr>
                <th>User</th>
                <th>Channel</th>
                <th>Started</th>
                <th>Duration</th>
                <th>IP</th>
            </tr>
    """
    
    if history:
        for entry in reversed(history):
            minutes = entry['duration'] // 60
            seconds = entry['duration'] % 60
            duration_str = f"{minutes}m {seconds}s"
            start_time = entry['start'].strftime("%H:%M:%S")
            
            html += f"""
            <tr>
                <td>{entry['user']}</td>
                <td>{entry['channel']}</td>
                <td>{start_time}</td>
                <td>{duration_str}</td>
                <td>{entry['ip']}</td>
            </tr>
            """
    else:
        html += '<tr><td colspan="5" style="text-align: center; color: #888;">No recent activity</td></tr>'
    
    html += """
        </table>
    </body>
    </html>
    """
    
    return html

@app.route('/')
def home():
    return "Xtream bridge active! Use /get.php?username=john&password=pass123&type=m3u_plus"
