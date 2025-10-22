from flask import Flask, request, Response, jsonify, redirect
import requests
from datetime import datetime
from collections import defaultdict
import time, re

app = Flask(__name__)

# =========================
# CONFIG
# =========================

# Default (for everyone else)
DEFAULT_M3U = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"
DEFAULT_EPG = "http://m3u4u.com/epg/w16vy52exeax15kzn39p"

# Ian & Harry custom source
SPECIAL_USERS = {
    "ian": {
        "m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j",
        "epg": "http://m3u4u.com/epg/p87vnr8dzdu4w2r1n41j"
    },
    "harry": {
        "m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j",
        "epg": "http://m3u4u.com/epg/p87vnr8dzdu4w2r1n41j"
    }
}

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

# =========================
# GLOBALS
# =========================

active_sessions = {}
connection_history = []
user_stats = defaultdict(lambda: {"total_fetches": 0, "last_fetch": None})
cached_m3u = {}
cached_channels = {}
cached_categories = {}
cache_time = {}

# =========================
# FUNCTIONS
# =========================

def parse_m3u(content):
    """Parse M3U into structured channel list"""
    channels, categories = [], {}
    try:
        text = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content
        lines = text.split("\n")
        current_channel = {}
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                current_channel = {
                    "num": len(channels) + 1,
                    "name": "Unknown Channel",
                    "stream_icon": "",
                    "stream_id": len(channels) + 1,
                    "category_id": "1",
                    "category_name": "Uncategorized",
                    "tvg_id": "",
                    "stream_url": ""
                }
                if "," in line:
                    current_channel["name"] = line.split(",", 1)[1].strip()
                group_match = re.search(r'group-title="([^"]*)"', line)
                if group_match:
                    cat = group_match.group(1)
                    current_channel["category_name"] = cat
                    if cat not in categories:
                        categories[cat] = str(len(categories) + 1)
                    current_channel["category_id"] = categories[cat]
                logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                if logo_match:
                    current_channel["stream_icon"] = logo_match.group(1)
            elif line and not line.startswith("#"):
                if current_channel:
                    current_channel["stream_url"] = line
                    channels.append(current_channel.copy())
                    current_channel = {}
    except Exception as e:
        print("M3U Parse Error:", e)
    return channels, categories

def get_user_urls(username):
    username = username.lower()
    info = SPECIAL_USERS.get(username)
    if info:
        return info["m3u"], info["epg"]
    return DEFAULT_M3U, DEFAULT_EPG

def get_cached_channels(username):
    """Fetch M3U per user with caching"""
    global cached_m3u, cached_channels, cached_categories, cache_time
    m3u_url, _ = get_user_urls(username)
    now = time.time()

    if m3u_url in cached_channels and now - cache_time.get(m3u_url, 0) < 300:
        return cached_channels[m3u_url], cached_categories[m3u_url], cached_m3u[m3u_url]

    try:
        resp = requests.get(m3u_url, timeout=10)
        if resp.status_code == 200:
            cached_m3u[m3u_url] = resp.content
            chans, cats = parse_m3u(resp.content)
            cached_channels[m3u_url] = chans
            cached_categories[m3u_url] = cats
            cache_time[m3u_url] = now
            print(f"Fetched {len(chans)} channels for {username} from {m3u_url}")
            return chans, cats, resp.content
    except Exception as e:
        print("Fetch M3U error:", e)
    return [], {}, None

def generate_session_id(username):
    return f"{username}_{request.remote_addr}_{int(time.time()*1000)}"

def check_auth():
    u = request.args.get("username","")
    p = request.args.get("password","")
    if u not in VALID_USERS or VALID_USERS[u] != p:
        return None
    return u

def check_admin_auth():
    return request.args.get("password","") == ADMIN_PASSWORD

# =========================
# ROUTES
# =========================

@app.route("/get.php")
def get_php():
    username = check_auth()
    if not username:
        return Response("Bad credentials", status=403)
    chans, cats, m3u = get_cached_channels(username)
    if not m3u:
        return Response("No playlist", status=500)
    return Response(m3u, mimetype="application/x-mpegURL")

@app.route("/xmltv.php")
def xmltv():
    username = check_auth()
    if not username:
        return Response("Bad credentials", status=403)
    _, epg_url = get_user_urls(username)
    try:
        resp = requests.get(epg_url, timeout=10)
        return Response(resp.content, mimetype="application/xml", status=resp.status_code)
    except Exception as e:
        return Response(f"Error fetching EPG: {e}", status=500)

# (Include your existing /player_api.php, /admin/dashboard, etc. unchanged from THIS.py)

@app.route("/")
def home():
    return "<h2>Xtream Bridge Running ✅</h2><p>Try /get.php?username=ian&password=October2025</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
