from flask import Flask, request, Response, jsonify, redirect
import requests
from datetime import datetime
import time
import re

app = Flask(__name__)

# ======================
# CONFIG
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

ADMIN_PASSWORD = "admin123"

USER_LINKS = {
    "dad":   {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "john":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "mark":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "james": {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "ian":   {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "harry": {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "main":  {"m3u": "http://m3u4u.com/m3u/476rnmqd4ds4rkd3nekg", "epg": "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"},
}

CACHE_TTL_SECONDS = 600  # 10 minutes
per_user_cache = {}

# ======================
# HELPERS
# ======================
def check_auth():
    u = request.args.get("username", "")
    p = request.args.get("password", "")
    if u in VALID_USERS and VALID_USERS[u] == p:
        return u
    return None

def check_admin():
    return request.args.get("password", "") == ADMIN_PASSWORD

def now_ts():
    return int(time.time())

def parse_m3u(content_bytes):
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
        channels = [{
            "num": 1,
            "name": f"Parser Error: {e}",
            "stream_icon": "",
            "stream_id": 1,
            "category_id": "1",
            "category_name": "Uncategorized",
            "tvg_id": "",
            "stream_url": "",
        }]
        categories = {"Uncategorized": "1"}
    return channels, categories

def refresh_user_cache(username, force=False):
    if username not in USER_LINKS:
        return False, "No links configured for this user"
    entry = per_user_cache.get(username)
    if not force and entry and (now_ts() - entry["fetched_at"] < CACHE_TTL_SECONDS):
        return True, None
    try:
        resp = requests.get(USER_LINKS[username]["m3u"], timeout=15)
        if resp.status_code != 200:
            return False, f"M3U fetch failed: {resp.status_code}"
        channels, categories = parse_m3u(resp.content)
        per_user_cache[username] = {"fetched_at": now_ts(), "channels": channels, "categories": categories}
        return True, None
    except Exception as e:
        return False, str(e)

# ======================
# ROUTES
# ======================

@app.route("/")
def index():
    lines = ["=== IPTV Access Links ===", ""]
    for user, links in USER_LINKS.items():
        lines.append(f"User: {user}")
        lines.append(f"M3U: {links['m3u']}")
        lines.append(f"EPG: {links['epg']}\n")
    lines.append("=========================")
    return Response("\n".join(lines), mimetype="text/plain")

@app.route("/get.php")
def get_php():
    username = check_auth()
    if not username:
        return Response("Invalid credentials", status=403)
    return redirect(USER_LINKS[username]["m3u"])

@app.route("/xmltv.php")
def xmltv():
    username = check_auth()
    if not username:
        return Response("Invalid credentials", status=403)
    return redirect(USER_LINKS[username]["epg"])

@app.route("/player_api.php")
def player_api():
    username = check_auth()
    if not username:
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})

    action = request.args.get("action", "")

    # ---- Xtream Codes base info ----
    if not action:
        host_parts = request.host.split(":")
        host = host_parts[0]
        port = host_parts[1] if len(host_parts) > 1 else "8080"

        return jsonify({
            "user_info": {
                "username": username,
                "password": VALID_USERS[username],
                "message": "",
                "auth": 1,
                "status": "Active",
                "exp_date": "1970-01-01 00:00:00",
                "is_trial": "0",
                "active_cons": "1",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "max_connections": "1",
            },
            "server_info": {
                "url": host,
                "port": port,
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "25462",
                "timezone": "Europe/London",
                "timestamp_now": int(time.time()),
                "time_now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    # ---- EPG / OpenTV Fix ----
    if action == "get_simple_data_table":
        epg_url = USER_LINKS[username]["epg"]
        if not epg_url:
            return jsonify({"epg_listings": [], "now_playing": {"programs": []}})

        if "epg_cache" not in per_user_cache:
            per_user_cache["epg_cache"] = {}
        epg_cache = per_user_cache["epg_cache"]

        cache_entry = epg_cache.get(username)
        if cache_entry and (now_ts() - cache_entry["fetched_at"] < CACHE_TTL_SECONDS):
            epg_data = cache_entry["data"]
        else:
            epg_data = []
            try:
                resp = requests.get(epg_url, timeout=15)
                from xml.etree import ElementTree
                tree = ElementTree.fromstring(resp.content)
                for prog in tree.findall("programme"):
                    channel = prog.attrib.get("channel", "")
                    start_raw = prog.attrib.get("start", "")[:14]
                    stop_raw = prog.attrib.get("stop", "")[:14]
                    try:
                        start_fmt = f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:8]} {start_raw[8:10]}:{start_raw[10:12]}:{start_raw[12:14]}"
                        stop_fmt = f"{stop_raw[:4]}-{stop_raw[4:6]}-{stop_raw[6:8]} {stop_raw[8:10]}:{stop_raw[10:12]}:{stop_raw[12:14]}"
                    except Exception:
                        continue
                    title = prog.findtext("title", default="(No title)")
                    desc = prog.findtext("desc", default="")
                    def to_ts(t):
                        try:
                            return int(time.mktime(datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timetuple()))
                        except Exception:
                            return 0
                    start_ts, stop_ts = to_ts(start_fmt), to_ts(stop_fmt)
                    epg_data.append({
                        "id": channel,
                        "title": title,
                        "start": start_fmt,
                        "end": stop_fmt,
                        "start_timestamp": start_ts,
                        "stop_timestamp": stop_ts,
                        "description": desc
                    })
                epg_cache[username] = {"fetched_at": now_ts(), "data": epg_data}
            except Exception:
                return jsonify({"epg_listings": [], "now_playing": {"programs": []}})

        now_ts_val = int(time.time())
        now_playing = [
            epg for epg in epg_data if epg["start_timestamp"] <= now_ts_val <= epg["stop_timestamp"]
        ]
        return jsonify({
            "epg_listings": epg_data,
            "now_playing": {"programs": now_playing if now_playing else []}
        })

    # ---- Live ----
    ok, err = refresh_user_cache(username)
    if not ok:
        return jsonify({"error": err}), 503
    cache = per_user_cache.get(username)
    channels = cache["channels"]
    categories = cache["categories"]

    if action == "get_live_categories":
        return jsonify([{"category_id": cid, "category_name": cname, "parent_id": 0}
                        for cname, cid in categories.items()])

    if action == "get_live_streams":
        category_id = request.args.get("category_id", "")
        return jsonify([
            {
                "num": ch["num"],
                "name": ch["name"],
                "stream_type": "live",
                "stream_id": ch["stream_id"],
                "stream_icon": ch["stream_icon"],
                "category_id": ch["category_id"],
                "direct_source": ch["stream_url"],
                "epg_channel_id": ch["tvg_id"],
            }
            for ch in channels if not category_id or ch["category_id"] == category_id
        ])

    # ---- Short EPG (Fix for IPTV Smarters) ----
    if action == "get_short_epg":
        stream_id = request.args.get("stream_id")
        now_ts_val = int(time.time())
        return jsonify({
            "epg_listings": [
                {
                    "id": stream_id,
                    "title": "No EPG Data",
                    "start_timestamp": now_ts_val - 600,
                    "stop_timestamp": now_ts_val + 1800,
                    "start": datetime.utcfromtimestamp(now_ts_val - 600).strftime("%Y-%m-%d %H:%M:%S"),
                    "end": datetime.utcfromtimestamp(now_ts_val + 1800).strftime("%Y-%m-%d %H:%M:%S"),
                    "description": "",
                }
            ]
        })

    # ---- Dummy VOD & Series ----
    if action in ["get_vod_categories", "get_vod_streams", "get_series", "get_series_categories"]:
        return jsonify([])

    return jsonify({"error": "Unsupported action"}), 400

# ======================
# Xtream-style live route (302 redirect)
# ======================
@app.route("/live/<username>/<password>/<int:stream_id>.ts")
def serve_live(username, password, stream_id):
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Invalid credentials", status=403)
    ok, err = refresh_user_cache(username)
    if not ok:
        return Response(f"Failed to refresh playlist: {err}", status=503)
    cache = per_user_cache.get(username)
    channels = cache["channels"]
    stream = next((ch for ch in channels if ch["stream_id"] == stream_id), None)
    if not stream:
        return Response("Stream not found", status=404)
    return redirect(stream["stream_url"])  # lightweight redirect

# ---- Smarters Lite alternate route (/username/password/id) ----
@app.route("/<username>/<password>/<int:stream_id>")
def serve_live_alt(username, password, stream_id):
    return redirect(f"/live/{username}/{password}/{stream_id}.ts", code=302)

# ======================
# ADMIN
# ======================
@app.route("/admin/refresh_cache")
def admin_refresh_cache():
    if not check_admin():
        return Response("Access denied", status=403)
    target = request.args.get("user", "")
    result = {}
    users = [target] if target else VALID_USERS.keys()
    for u in users:
        ok, err = refresh_user_cache(u, force=True)
        result[u] = {"ok": ok, "error": err}
    return jsonify({
        "success": True,
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": result
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
