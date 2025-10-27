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

USER_LINKS = {
    "dad":   {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "john":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "mark":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "james": {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "ian":   {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "harry": {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "main":  {"m3u": "http://m3u4u.com/m3u/476rnmqd4ds4rkd3nekg", "epg": "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"},
}

# ======================
# HELPERS
# ======================
def check_auth():
    u = request.args.get("username", "")
    p = request.args.get("password", "")
    if u in VALID_USERS and VALID_USERS[u] == p:
        return u
    return None


def parse_m3u(content_bytes):
    """Parse M3U playlist into channel list and category map"""
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

                if "," in line:
                    current["name"] = line.split(",", 1)[1].strip()

                m = re.search(r'group-title="([^"]*)"', line)
                cat_name = m.group(1) if m else "Uncategorized"
                if cat_name not in categories:
                    categories[cat_name] = str(len(categories) + 1)
                current["category_name"] = cat_name
                current["category_id"] = categories[cat_name]

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
        print(f"M3U Parse error: {e}")
    return channels, categories


# ======================
# ROUTES
# ======================
@app.route("/")
def index():
    """Show all available user links"""
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

    # --- Default login info (for Smarters) ---
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
                "rtmp_port": "1935",
                "timezone": "UTC",
                "timestamp_now": str(int(time.time())),
                "time_now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        })

    # --- Get live categories ---
    if action == "get_live_categories":
        try:
            resp = requests.get(USER_LINKS[username]["m3u"], timeout=10)
            channels, categories = parse_m3u(resp.content)
            return jsonify([
                {"category_id": cid, "category_name": cname, "parent_id": 0}
                for cname, cid in categories.items()
            ])
        except Exception:
            return jsonify([])

    # --- Get live streams ---
    if action == "get_live_streams":
        category_id = request.args.get("category_id", "")
        try:
            resp = requests.get(USER_LINKS[username]["m3u"], timeout=10)
            channels, categories = parse_m3u(resp.content)
            return jsonify([
                {
                    "num": ch["num"],
                    "name": ch["name"],
                    "stream_type": "live",
                    "stream_id": ch["stream_id"],
                    "stream_icon": ch["stream_icon"],
                    "category_id": ch["category_id"],
                    "direct_source": f"https://{request.host}/live/{username}/{VALID_USERS[username]}/{ch['stream_id']}.ts",
                    "epg_channel_id": ch["tvg_id"],
                }
                for ch in channels if not category_id or ch["category_id"] == category_id
            ])
        except Exception:
            return jsonify([])

    return jsonify([])


# ======================
# STREAM HANDLERS
# ======================

@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_proxy(username, password, stream_id, ext):
    """Proxy the stream over HTTPS (fixes iOS playback issues)"""
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Invalid login", status=403)
    try:
        resp = requests.get(USER_LINKS[username]["m3u"], timeout=10)
        channels, _ = parse_m3u(resp.content)
        for ch in channels:
            if ch["stream_id"] == stream_id:
                headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://m3u4u.com/"}
                r = requests.get(ch["stream_url"], headers=headers, stream=True)
                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type=r.headers.get("content-type", "video/MP2T"),
                )
    except Exception as e:
        print(f"Proxy stream error: {e}")
    return Response("Stream not found", status=404)


@app.route("/<username>/<password>/<int:stream_id>")
def live_fallback(username, password, stream_id):
    """Handle apps that request /user/pass/id instead of /live/user/pass/id.ts"""
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Invalid login", status=403)
    try:
        resp = requests.get(USER_LINKS[username]["m3u"], timeout=10)
        channels, _ = parse_m3u(resp.content)
        for ch in channels:
            if ch["stream_id"] == stream_id:
                headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://m3u4u.com/"}
                r = requests.get(ch["stream_url"], headers=headers, stream=True)
                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type=r.headers.get("content-type", "video/MP2T"),
                )
    except Exception as e:
        print(f"Live fallback error: {e}")
    return Response("Stream not found", status=404)


# ======================
# RUN APP
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
