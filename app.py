from flask import Flask, request, Response, jsonify, redirect
import requests
from datetime import datetime
import time
import re

app = Flask(__name__)

# ======================
# CONFIGURATION
# ======================

VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin",
}

# --- Use your GitHub-hosted playlist ---
GITHUB_M3U = "https://raw.githubusercontent.com/StainlessENG/ian-sports/main/m3u4u-102864-671117-Playlist.m3u"
EPG_URL = "http://m3u4u.com/epg/w16vy52exeax15kzn39p"

USER_LINKS = {u: {"m3u": GITHUB_M3U, "epg": EPG_URL} for u in VALID_USERS}

# --- Cache for GitHub fetch ---
_cache = {"timestamp": 0, "data": b""}
CACHE_TTL = 300  # 5 minutes


# ======================
# HELPERS
# ======================

def check_auth():
    """Simple username/password check"""
    u = request.args.get("username", "")
    p = request.args.get("password", "")
    if u in VALID_USERS and VALID_USERS[u] == p:
        return u
    return None


def fetch_m3u():
    """Fetch M3U file from GitHub with caching"""
    now = time.time()
    if now - _cache["timestamp"] < CACHE_TTL and _cache["data"]:
        return _cache["data"]

    try:
        r = requests.get(GITHUB_M3U, timeout=10)
        if r.status_code == 200:
            _cache["data"] = r.content
            _cache["timestamp"] = now
            return r.content
    except Exception as e:
        print(f"Fetch error: {e}")

    return _cache["data"]


def parse_m3u(content_bytes):
    """Parse M3U playlist into channel and category lists"""
    channels = []
    categories = {}
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        current = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXTINF:"):
                current = {
                    "num": len(channels) + 1,
                    "name": "Unknown",
                    "stream_icon": "",
                    "stream_id": len(channels) + 1,
                    "category_id": "1",
                    "category_name": "Uncategorized",
                    "tvg_id": "",
                    "stream_url": "",
                }

                # Channel name
                if "," in line:
                    current["name"] = line.split(",", 1)[1].strip()

                # Category
                m = re.search(r'group-title="([^"]*)"', line)
                cat_name = m.group(1) if m else "Uncategorized"
                if cat_name not in categories:
                    categories[cat_name] = str(len(categories) + 1)
                current["category_name"] = cat_name
                current["category_id"] = categories[cat_name]

                # TVG ID / logo
                m = re.search(r'tvg-id="([^"]*)"', line)
                if m:
                    current["tvg_id"] = m.group(1)

                m = re.search(r'tvg-logo="([^"]*)"', line)
                if m:
                    current["stream_icon"] = m.group(1)

            elif not line.startswith("#"):
                if current:
                    current["stream_url"] = line
                    channels.append(current)
                    current = None

        for idx, ch in enumerate(channels, start=1):
            ch["num"] = idx
            ch["stream_id"] = idx

    except Exception as e:
        print(f"M3U parse error: {e}")
    return channels, categories


# ======================
# ROUTES
# ======================

@app.route("/")
def index():
    lines = ["=== IPTV Access Links ===", ""]
    for user, links in USER_LINKS.items():
        lines.append(f"User: {user}")
        lines.append(f"M3U: /get.php?username={user}&password={VALID_USERS[user]}")
        lines.append(f"EPG: /xmltv.php?username={user}&password={VALID_USERS[user]}\n")
    lines.append("=========================")
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/get.php")
def get_php():
    username = check_auth()
    if not username:
        return Response("Invalid credentials", status=403)
    return redirect(USER_LINKS[username]["m3u"], code=302)


@app.route("/xmltv.php")
def xmltv():
    username = check_auth()
    if not username:
        return Response("Invalid credentials", status=403)
    return redirect(USER_LINKS[username]["epg"], code=302)


@app.route("/player_api.php")
def player_api():
    username = check_auth()
    if not username:
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})

    action = request.args.get("action", "")

    # --- Login info (default) ---
    if not action:
        return jsonify({
            "user_info": {
                "username": username,
                "password": VALID_USERS[username],
                "auth": 1,
                "status": "Active",
                "exp_date": "1780185600",
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1609459200",
                "max_connections": "2",
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": request.host,
                "port": "8080",
                "https_port": "443",
                "server_protocol": "https",
                "timezone": "
