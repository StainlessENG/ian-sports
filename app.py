from flask import Flask, request, Response, jsonify, redirect
import requests
from datetime import datetime
from collections import defaultdict
import time
import re

app = Flask(__name__)

# =====================================================
# CONFIGURATION
# =====================================================

# Use jsDelivr CDN for better speed & reliability
M3U_URL = "https://cdn.jsdelivr.net/gh/StainlessENG/ian-sports@main/m3u4u-102864-670937-Playlist.m3u"
EPG_URL = "http://m3u4u.com/epg/w16vy52exeax15kzn39p"

VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025"
}

MAX_CONNECTIONS_PER_USER = 2
ADMIN_PASSWORD = "admin123"

# =====================================================
# GLOBALS
# =====================================================

active_sessions = {}
connection_history = []
user_stats = defaultdict(lambda: {"total_fetches": 0, "last_fetch": None})
cached_m3u = None
cached_channels = []
cached_categories = {}
cache_time = 0


# =====================================================
# HELPERS
# =====================================================

def parse_m3u(content):
    channels = []
    categories = {}
    try:
        text = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else content
        lines = text.splitlines()
        current_channel = {}

        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                current_channel = {
                    'num': len(channels) + 1,
                    'name': 'Unknown Channel',
                    'stream_icon': '',
                    'stream_id': len(channels) + 1,
                    'category_id': '1',
                    'category_name': 'Uncategorized',
                    'tvg_id': '',
                    'stream_url': ''
                }

                # Name
                if ',' in line:
                    current_channel['name'] = line.split(',', 1)[1].strip()

                # Category
                m = re.search(r'group-title="([^"]*)"', line)
                if m:
                    cat = m.group(1)
                    if cat not in categories:
                        categories[cat] = str(len(categories) + 1)
                    current_channel['category_name'] = cat
                    current_channel['category_id'] = categories[cat]

                # TVG ID
                m = re.search(r'tvg-id="([^"]*)"', line)
                if m:
                    current_channel['tvg_id'] = m.group(1)

                # Logo
                m = re.search(r'tvg-logo="([^"]*)"', line)
                if m:
                    current_channel['stream_icon'] = m.group(1)

            elif line and not line.startswith('#'):
                if current_channel:
                    current_channel['stream_url'] = line
                    channels.append(current_channel.copy())
                    current_channel = {}

    except Exception as e:
        print(f"M3U parse error: {e}")

    return channels, categories


def get_cached_channels():
    """Cache playlist for 24h to reduce GitHub requests"""
    global cached_channels, cached_categories, cache_time, cached_m3u
    if time.time() - cache_time < 86400 and cached_channels and cached_categories:
        return cached_channels, cached_categories, cached_m3u

    try:
        print("🔄 Fetching playlist from GitHub...")
        resp = requests.get(M3U_URL, timeout=45)
        if resp.status_code == 200:
            cached_m3u = resp.content
            cached_channels, cached_categories = parse_m3u(resp.content)
            cache_time = time.time()
            print(f"✅ Loaded {len(cached_channels)} channels.")
        else:
            print(f"⚠️ M3U fetch failed: HTTP {resp.status_code}")
    except Exception as e:
        print(f"Error fetching M3U: {e}")

    return cached_channels, cached_categories, cached_m3u


def check_auth():
    u = request.args.get('username', '')
    p = request.args.get('password', '')
    if u in VALID_USERS and VALID_USERS[u] == p:
        return u
    return None


def check_admin_auth():
    return request.args.get('password', '') == ADMIN_PASSWORD


def get_user_active_sessions(username):
    return sum(1 for s in active_sessions.values() if s['user'] == username)


# =====================================================
# ROUTES
# =====================================================

@app.route('/')
def home():
    channels, categories, _ = get_cached_channels()
    return f"""
    <html><head><title>Xtream Bridge</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:40px;">
    <h1>📺 Xtream Bridge Online</h1>
    <p>{len(channels)} channels across {len(categories)} categories.</p>
    <p>Use your IPTV app with:</p>
    <code>Server: {request.host_url}<br>Username: john<br>Password: pass123</code>
    </body></html>
    """


@app.route('/get.php')
def get_php():
    username = check_auth()
    if not username:
        return Response("Invalid login", status=403)

    if get_user_active_sessions(username) >= MAX_CONNECTIONS_PER_USER:
        return Response("Connection limit reached", status=429)

    channels, categories, m3u_content = get_cached_channels()
    if not m3u_content:
        return Response("Could not fetch M3U", status=500)

    return Response(m3u_content, mimetype='application/x-mpegURL')


@app.route('/xmltv.php')
def xmltv():
    username = check_auth()
    if not username:
        return Response("Invalid login", status=403)
    try:
        r = requests.get(EPG_URL, timeout=20)
        return Response(r.content, mimetype='application/xml')
    except Exception as e:
        return Response(f"EPG fetch failed: {e}", status=500)


@app.route('/player_api.php')
def player_api():
    username = check_auth()
    if not username:
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})

    action = request.args.get('action', '')
    channels, categories, _ = get_cached_channels()

    if not action:
        return jsonify({
            "user_info": {
                "username": username,
                "password": VALID_USERS[username],
                "auth": 1,
                "status": "Active",
                "exp_date": "1780185600",
                "max_connections": str(MAX_CONNECTIONS_PER_USER)
            },
            "server_info": {
                "url": request.host,
                "port": "8080",
                "https_port": "443",
                "server_protocol": "https",
                "timezone": "UTC",
                "timestamp_now": str(int(time.time()))
            }
        })

    if action == "get_live_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cname, cid in categories.items()
        ])

    if action == "get_live_streams":
        category_id = request.args.get('category_id', '')
        streams = []
        for ch in channels:
            if category_id and ch.get("category_id") != category_id:
                continue
            streams.append({
                "num": ch["num"],
                "name": ch["name"],
                "stream_type": "live",
                "stream_id": ch["stream_id"],
                "stream_icon": ch["stream_icon"],
                "category_id": ch["category_id"],
                "epg_channel_id": ch["tvg_id"],
                "direct_source": ch["stream_url"]
            })
        return jsonify(streams)

    return jsonify([])


@app.route('/live/<username>/<password>/<int:stream_id>.ts')
def live(username, password, stream_id):
    """Proxy the stream so IPTV Lite works correctly"""
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Unauthorized", status=403)

    channels, _, _ = get_cached_channels()
    for ch in channels:
        if ch["stream_id"] == stream_id:
            try:
                r = requests.get(ch["stream_url"], stream=True, timeout=10)
                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type=r.headers.get("content-type", "video/mp2t")
                )
            except Exception as e:
                print(f"Proxy error: {e}")
                return Response("Stream fetch failed", status=502)
    return Response("Stream not found", status=404)


@app.route('/admin/refresh_m3u')
def refresh_m3u():
    if not check_admin_auth():
        return Response("Access denied", status=403)
    global cache_time
    cache_time = 0
    channels, categories, _ = get_cached_channels()
    return jsonify({"ok": True, "channels": len(channels), "categories": len(categories)})


@app.route('/admin/dashboard')
def dashboard():
    if not check_admin_auth():
        return Response("Access denied", status=403)
    channels, categories, _ = get_cached_channels()
    html = f"<h1>Xtream Dashboard</h1><p>Channels: {len(channels)}<br>Categories: {len(categories)}</p>"
    return html


# =====================================================
# MAIN
# =====================================================

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
