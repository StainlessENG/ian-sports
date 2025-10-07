from flask import Flask, request, Response, jsonify, render_template_string
import requests
from datetime import datetime
from collections import defaultdict
import time

app = Flask(__name__)

# --- CONFIG ---
M3U_URL = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"
EPG_URL = "http://websafety101.net:5050/xmltv.php?username=chulobonao7@aol.com&password=TQRfqAp9dA"
VALID_USERS = {"sid": "devon", "john": "pass123"}
MAX_CONNECTIONS_PER_USER = 2  # Max simultaneous M3U fetches allowed
ADMIN_PASSWORD = "admin123"  # Password to access dashboard
# ----------------

# Global tracking
active_sessions = {}  # {session_id: {user, ip, channel, start_time}}
connection_history = []  # List of past connections
user_stats = defaultdict(lambda: {"total_fetches": 0, "last_fetch": None})

def generate_session_id(username):
    """Generate unique session ID"""
    return f"{username}_{request.remote_addr}_{int(time.time() * 1000)}"

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

def get_user_active_sessions(username):
    """Count active sessions for a user"""
    return sum(1 for s in active_sessions.values() if s['user'] == username)

@app.route('/get.php')
def get_php():
    username = check_auth()
    if not username:
        return Response("User not found or bad password", status=403)
    
    # Check connection limit
    if get_user_active_sessions(username) >= MAX_CONNECTIONS_PER_USER:
        return Response(f"Connection limit reached ({MAX_CONNECTIONS_PER_USER} max). Close other streams first.", status=429)
    
    # Create new session
    session_id = generate_session_id(username)
    active_sessions[session_id] = {
        'user': username,
        'ip': request.remote_addr,
        'channel': 'M3U Playlist',
        'start_time': datetime.now()
    }
    
    # Update stats
    user_stats[username]['total_fetches'] += 1
    user_stats[username]['last_fetch'] = datetime.now()
    
    # Fetch M3U
    resp = requests.get(M3U_URL)
    if resp.status_code != 200:
        del active_sessions[session_id]
        return Response("Could not fetch M3U", status=500)
    
    # Log to history
    connection_history.append({
        'user': username,
        'ip': request.remote_addr,
        'action': 'M3U Fetch',
        'time': datetime.now()
    })
    
    # Keep only last 100 history entries
    if len(connection_history) > 100:
        connection_history.pop(0)
    
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
    
    # Log EPG fetch
    connection_history.append({
        'user': username,
        'ip': request.remote_addr,
        'action': 'EPG Fetch',
        'time': datetime.now()
    })
    
    if len(connection_history) > 100:
        connection_history.pop(0)
    
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
                "active_cons": str(get_user_active_sessions(username)),
                "max_connections": str(MAX_CONNECTIONS_PER_USER)
            }
        })

@app.route('/admin/kick/<session_id>')
def kick_session(session_id):
    """Manually kick a session"""
    if not check_admin_auth():
        return Response("Access denied", status=403)
    
    if session_id in active_sessions:
        user = active_sessions[session_id]['user']
        del active_sessions[session_id]
        return jsonify({"success": True, "message": f"Kicked session for {user}"})
    
    return jsonify({"success": False, "message": "Session not found"})

@app.route('/admin/kick_user/<username>')
def kick_user(username):
    """Kick all sessions for a user"""
    if not check_admin_auth():
        return Response("Access denied", status=403)
    
    to_remove = [sid for sid, s in active_sessions.items() if s['user'] == username]
    for sid in to_remove:
        del active_sessions[sid]
    
    return jsonify({"success": True, "message": f"Kicked {len(to_remove)} session(s) for {username}"})

@app.route('/admin/dashboard')
def admin_dashboard():
    if not check_admin_auth():
        return Response("Access denied. Use ?password=admin123", status=403)
    
    sessions = list(active_sessions.items())
    history = list(connection_history[-30:])  # Last 30
    stats = dict(user_stats)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Xtream Bridge Dashboard</title>
        <meta http-equiv="refresh" content="10">
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
            .info { background: #2a2a2a; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2196F3; }
        </style>
    </head>
    <body>
        <h1>🎬 Xtream Bridge Dashboard</h1>
        <p>Auto-refreshes every 10 seconds | Current time: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
        
        <div class="info">
            <strong>ℹ️ How It Works:</strong> Sessions are tracked when users fetch the M3U playlist. 
            Active sessions remain until manually kicked or the server restarts. This prevents connection limit bypassing.
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">""" + str(len(sessions)) + """</div>
                <div class="stat-label">Active Sessions</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">""" + str(len(VALID_USERS)) + """</div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">""" + str(len(history)) + """</div>
                <div class="stat-label">Recent Activity</div>
            </div>
        </div>
        
        <h2>🔴 Active Sessions</h2>
        <table>
            <tr>
                <th>User</th>
                <th>Started</th>
                <th>Duration</th>
                <th>IP Address</th>
                <th>Action</th>
            </tr>
    """
    
    if sessions:
        for session_id, sess in sessions:
            duration = datetime.now() - sess['start_time']
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            seconds = duration.seconds % 60
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            start_time = sess['start_time'].strftime("%H:%M:%S")
            
            kick_url = f"/admin/kick/{session_id}?password={ADMIN_PASSWORD}"
            
            html += f"""
            <tr>
                <td><strong>{sess['user']}</strong></td>
                <td>{start_time}</td>
                <td>{duration_str}</td>
                <td>{sess['ip']}</td>
                <td><a href="{kick_url}"><button class="kick-btn">KICK</button></a></td>
            </tr>
            """
    else:
        html += '<tr><td colspan="5" style="text-align: center; color: #888;">No active sessions</td></tr>'
    
    html += """
        </table>
        
        <h2>📊 User Statistics</h2>
        <table>
            <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Active Sessions</th>
                <th>Total Fetches</th>
                <th>Last Activity</th>
                <th>Action</th>
            </tr>
    """
    
    for username in VALID_USERS:
        stat = stats.get(username, {"total_fetches": 0, "last_fetch": None})
        active_count = get_user_active_sessions(username)
        is_online = active_count > 0
        status = f'<span class="online">● ONLINE ({active_count})</span>' if is_online else '<span class="offline">● OFFLINE</span>'
        
        last_seen = stat['last_fetch'].strftime("%Y-%m-%d %H:%M:%S") if stat['last_fetch'] else "Never"
        
        kick_url = f"/admin/kick_user/{username}?password={ADMIN_PASSWORD}"
        kick_btn = f'<a href="{kick_url}"><button class="kick-btn">KICK ALL</button></a>' if is_online else '-'
        
        html += f"""
        <tr>
            <td><strong>{username}</strong></td>
            <td>{status}</td>
            <td>{active_count} / {MAX_CONNECTIONS_PER_USER}</td>
            <td>{stat['total_fetches']}</td>
            <td>{last_seen}</td>
            <td>{kick_btn}</td>
        </tr>
        """
    
    html += """
        </table>
        
        <h2>📜 Recent Activity (Last 30)</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>IP</th>
            </tr>
    """
    
    if history:
        for entry in reversed(history):
            time_str = entry['time'].strftime("%H:%M:%S")
            
            html += f"""
            <tr>
                <td>{time_str}</td>
                <td><strong>{entry['user']}</strong></td>
                <td>{entry['action']}</td>
                <td>{entry['ip']}</td>
            </tr>
            """
    else:
        html += '<tr><td colspan="4" style="text-align: center; color: #888;">No recent activity</td></tr>'
    
    html += """
        </table>
    </body>
    </html>
    """
    
    return html

@app.route('/')
def home():
    return "Xtream bridge active! Use /get.php?username=john&password=pass123&type=m3u_plus"
