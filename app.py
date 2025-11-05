import time, re, requests
from collections import defaultdict
from flask import Flask, request, redirect, jsonify, Response

app = Flask(__name__)

# --------- CONFIG ---------
USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Your direct RAW GitHub M3U URL
M3U_URL = "https://raw.githubusercontent.com/StainlessENG/ian-sports/refs/heads/main/Main%20Playlist.m3u"

CACHE_TTL = 600  # seconds
# --------------------------

_m3u_cache = {"ts": 0, "text": "", "parsed": None}

def valid_user(username, password):
    return username in USERS and USERS[username] == password

def fetch_m3u():
    """Fetch and cache M3U text."""
    now = time.time()
    if _m3u_cache["parsed"] is not None and (now - _m3u_cache["ts"] < CACHE_TTL):
        return _m3u_cache["parsed"]

    resp = requests.get(M3U_URL, timeout=15)
    resp.raise_for_status()
    text = resp.text

    parsed = parse_m3u(text)
    _m3u_cache["ts"] = now
    _m3u_cache["text"] = text
    _m3u_cache["parsed"] = parsed
    return parsed

def parse_m3u(text):
    """
    Parse an M3U into:
      - categories: list of {id, name}
      - streams: list of {stream_id, name, url, logo, epg_id, category_id}
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams = []
    cat_map = {}   # name -> id
    next_id = 1
    stream_id = 1

    # Regex to parse #EXTINF attributes
    # Example: #EXTINF:-1 tvg-id="bbc1" tvg-name="BBC One" tvg-logo="..." group-title="UK Freeview",BBC One
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            # Attributes
            attrs = dict(attr_re.findall(line))
            # Display name after last comma
            if "," in line:
                disp = line.split(",", 1)[1].strip()
            else:
                disp = attrs.get("tvg-name") or "Channel"

            # Next non-# line should be the URL
            url = ""
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            if j < len(lines):
                url = lines[j].strip()

            group = attrs.get("group-title") or "Uncategorised"
            logo = attrs.get("tvg-logo") or ""
            epg_id = attrs.get("tvg-id") or ""

            if group not in cat_map:
                cat_map[group] = next_id
                next_id += 1

            streams.append({
                "stream_id": stream_id,
                "name": disp,
                "url": url,
                "logo": logo,
                "epg_id": epg_id,
                "category_id": cat_map[group],
                "category_name": group
            })
            stream_id += 1
            i = j
        else:
            i += 1

    # Build categories list
    categories = [{"category_id": cid, "category_name": name, "parent_id": 0}
                  for name, cid in sorted(cat_map.items(), key=lambda x: x[1])]

    return {"categories": categories, "streams": streams}

@app.route("/")
def index():
    return "✅ Xtream Bridge OK (M3U redirect + Xtream categories/streams)"

@app.route("/get.php")
def get_m3u():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(M3U_URL)

@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action", "")

    if not valid_user(username, password):
        return jsonify({"user_info": {"auth": 0, "status": "Unauthorized"}})

    # --- LIVE CATEGORIES ---
    if action == "get_live_categories":
        data = fetch_m3u()
        return jsonify(data["categories"])

    # --- LIVE STREAMS (optionally filter by category_id) ---
    if action == "get_live_streams":
        data = fetch_m3u()
        cat_filter = request.args.get("category_id")
        out = []
        for s in data["streams"]:
            if cat_filter and str(s["category_id"]) != str(cat_filter):
                continue
            out.append({
                "num": str(s["stream_id"]),
                "name": s["name"],
                "stream_type": "live",
                "stream_id": s["stream_id"],
                "stream_icon": s["logo"],
                "epg_channel_id": s["epg_id"],
                "category_id": str(s["category_id"]),
                "direct_source": s["url"]  # helpful for some players
            })
        return jsonify(out)

    # Minimal stubs so players stop probing VOD/Series
    if action in ["get_vod_categories", "get_series_categories",
                  "get_vod_streams", "get_series"]:
        return jsonify([])

    # Default: user/server info
    return jsonify({
        "user_info": {
            "auth": 1,
            "username": username,
            "status": "Active",
            "exp_date": "UNLIMITED",
            "is_trial": "0",
            "active_cons": "1"
        },
        "server_info": {
            "url": "your-app-name.onrender.com",
            "port": 443,
            "https_port": 443,
            "server_protocol": "https"
        }
    })

# (Optional) If your player tries to play via /live/<u>/<p>/<id>.m3u8, you can add:
@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    data = fetch_m3u()
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            # simple redirect to the real stream URL
            return redirect(s["url"])
    return Response("Stream not found", status=404)

if __name__ == "__main__":
    # Use the port Render provides via $PORT in production
    import os
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
