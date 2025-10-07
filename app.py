from flask import Flask, request, Response, jsonify
import requests

app = Flask(__name__)

# --- CONFIG ---
M3U_URL = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"  # your m3u4u link
EPG_URL = "http://websafety101.net:5050/xmltv.php?username=chulobonao7@aol.com&password=TQRfqAp9dA"  # Add your EPG URL here (XMLTV format, usually ends in .xml or .gz)
VALID_USERS = {"sid": "devon", "john": "pass123"}  # username/password for login
# ----------------

def check_auth():
    """Check if username and password are valid"""
    username = request.args.get('username', '')
    password = request.args.get('password', '')
    
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return False
    return True

@app.route('/get.php')
def get_php():
    if not check_auth():
        return Response("User not found or bad password", status=403)
    
    resp = requests.get(M3U_URL)
    if resp.status_code != 200:
        return Response("Could not fetch M3U", status=500)
    
    return Response(resp.content, mimetype='application/x-mpegURL')

@app.route('/xmltv.php')
def xmltv():
    """EPG endpoint for XMLTV data"""
    if not check_auth():
        return Response("User not found or bad password", status=403)
    
    if not EPG_URL:
        return Response("EPG not configured", status=404)
    
    resp = requests.get(EPG_URL)
    if resp.status_code != 200:
        return Response("Could not fetch EPG", status=500)
    
    return Response(resp.content, mimetype='application/xml')

@app.route('/player_api.php')
def player_api():
    """Xtream Codes API endpoint"""
    if not check_auth():
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})
    
    action = request.args.get('action', '')
    
    if action == 'get_live_categories':
        return jsonify([{"category_id": "1", "category_name": "Live TV", "parent_id": 0}])
    
    elif action == 'get_live_streams':
        return jsonify([])
    
    elif action == 'get_vod_categories':
        return jsonify([])
    
    elif action == 'get_vod_streams':
        return jsonify([])
    
    elif action == 'get_series_categories':
        return jsonify([])
    
    elif action == 'get_series':
        return jsonify([])
    
    else:
        # Default: return user info
        return jsonify({
            "user_info": {
                "username": request.args.get('username'),
                "password": request.args.get('password'),
                "auth": 1,
                "status": "Active",
                "exp_date": "1999999999",
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1234567890",
                "max_connections": "1",
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": request.host_url.rstrip('/'),
                "port": "443",
                "https_port": "443",
                "server_protocol": "https",
                "rtmp_port": "1935",
                "timestamp_now": "1234567890",
                "time_now": "2024-01-01 00:00:00"
            }
        })

@app.route('/')
def home():
    return "Xtream bridge active! Use /get.php?username=john&password=pass123&type=m3u_plus"
