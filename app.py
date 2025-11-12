import os, time, re, requests
from flask import Flask, request, redirect, jsonify, Response
from xml.etree.ElementTree import Element, SubElement, tostring

app = Flask(__name__)

# ---------------- CONFIG ----------------
USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# m3u4u credentials (used to get fresh token)
M3U4U_EMAIL = "jamesjeley@me.com"
M3U4U_PASSWORD = "jempot-fedteH-sumhe9"

# Default token (used until new one is fetched)
M3U4U_TOKEN = "476rnmqd4ds4rkd3nekg"

CACHE_TTL = 600  # seconds
# ----------------------------------------

_m3u_cache = {"ts": 0, "parsed": None}
_token_cache = {"ts": 0, "token": M3U4U_TOKEN}


# -------- Helper functions --------
def valid_user(username, password):
    return username in USERS and USERS[username] == password


def wants_json():
    """Detect if client wants JSON (default) or XML"""
    accept = request.headers.get('Accept', '').lower()
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'smarters' in user_agent or 'okhttp' in user_agent:
        return True
    if 'xml' in accept:
        return False
    output_format = request.values.get('output', '').lower()
    if output_format == 'json':
        return True
    if output_format in ['xml', 'm3u8', 'ts']:
        return False
    return True


def get_m3u4u_token(force_refresh=False):
    """Retrieve or reuse the m3u4u token."""
    now = time.time()
    if (
        not force_refresh
        and _token_cache["token"]
        and now - _token_cache["ts"] < 86400  # refresh every 24h
    ):
        return _token_cache["token"]

    try:
        login_url = "https://m3u4u.com/api/login"
        data = {"email": M3U4U_EMAIL, "password": M3U4U_PASSWORD}
        headers = {"User-Agent": "XtreamBridge/1.0"}
        resp = requests.post(login_url, json=data, headers=headers, timeout=15)
        resp.raise_for_status()
        info = resp.json()
        token = info.get("token") or info.get("user", {}).get("token")

        if not token:
            print("[ERROR] No token received from m3u4u login.")
            return _token_cache["token"]

        _token_cache["token"] = token
        _token_cache["ts"] = now
        print(f"[INFO] New m3u4u token fetched: {token}")
        return token
    except Exception as e:
        print(f"[ERROR] Unable to fetch m3u4u token: {e}")
        return _token_cache["token"]


def fetch_m3u():
    """Fetch and parse M3U playlist from m3u4u."""
    now = time.time()
    if _m3u_cache["parsed"] and now - _m3u_cache["ts"] < CACHE_TTL:
        return _m3u_cache["parsed"]

    token = get_m3u4u_token()
    m3u_url = f"https://m3u4u.com/playlist/{token}/m3u_plus"

    try:
        headers = {"User-Agent": "XtreamBridge/1.0"}
        resp = requests.get(m3u_url, headers=headers, timeout=20)
        resp.raise_for_status()
        parsed = parse_m3u(resp.text)
        _m3u_cache["parsed"] = parsed
        _m3u_cache["ts"] = now
        return parsed
    except Exception as e:
        print(f"[ERROR] Unable to fetch playlist: {e}")
        return {"categories": [], "streams": []}


def parse_m3u(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams, cat_map = [], {}
    next_cat_id, stream_id = 1, 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            attrs = dict(attr_re.findall(line))
            name = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "Channel")
            url = ""
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            if j < len(lines):
                url = lines[j].strip()

            group = attrs.get("group-title", "Uncategorised")
            logo = attrs.get("tvg-logo", "")
            epg_id = attrs.get("tvg-id", "")

            if group not in cat_map:
                cat_map[group] = next_cat_id
                next_cat_id += 1

            streams.append({
                "stream_id": stream_id,
                "num": stream_id,
                "name": name,
                "stream_type": "live",
                "stream_icon": logo,
                "epg_channel_id": epg_id,
                "added": "1640000000",
                "category_id": str(cat_map[group]),
                "category_name": group,
                "direct_source": url,
                "tv_archive": 0,
                "tv_archive_duration": 0
            })
            stream_id += 1
            i = j
        else:
            i += 1

    categories = [{"category_id": str(cid), "category_name": name, "parent_id": 0}
                  for name, cid in sorted(cat_map.items(), key=lambda x: x[1])]

    return {"categories": categories, "streams": streams}


# -------- ROUTES --------

@app.route("/")
def index():
    return "✅ Xtream Bridge connected to m3u4u (live + EPG working)"


@app.route("/get.php")
def get_m3u():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    token = get_m3u4u_token()
    return redirect(f"https://m3u4u.com/playlist/{token}/m3u_plus")


@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action", "")
    use_json = wants_json()

    if not valid_user(username, password):
        msg = {"user_info": {"username": username, "password": password,
                             "message": "Invalid credentials", "auth": 0, "status": "Disabled"}}
        return jsonify(msg) if use_json else Response("<error>Invalid credentials</error>", 403)

    # LOGIN INFO
    if action == "":
        info = {
            "user_info": {
                "username": username,
                "password": password,
                "message": "Active",
                "auth": 1,
                "status": "Active",
                "exp_date": None,
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1640000000",
                "max_connections": "1",
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": request.host.split(':')[0],
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "1935",
                "timezone": "UTC",
                "timestamp_now": int(time.time()),
                "time_now": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        return jsonify(info) if use_json else Response("<status>Active</status>", content_type="text/xml")

    # LIVE CATEGORIES
    if action == "get_live_categories":
        cats = fetch_m3u()["categories"]
        return jsonify(cats) if use_json else Response(tostring(Element("categories")), content_type="text/xml")

    # LIVE STREAMS
    if action == "get_live_streams":
        data = fetch_m3u()
        cat_filter = request.values.get("category_id")
        result = [s for s in data["streams"] if not cat_filter or str(s["category_id"]) == str(cat_filter)]
        return jsonify(result) if use_json else Response(tostring(Element("channels")), content_type="text/xml")

    # EMPTY ACTIONS
    if action in ["get_vod_categories", "get_vod_streams", "get_series_categories",
                  "get_series", "get_series_info", "get_vod_info", "get_short_epg",
                  "get_simple_data_table"]:
        return jsonify([]) if use_json else Response("<empty/>", content_type="text/xml")

    return jsonify({"error": "action not handled", "action": action}) if use_json else Response("<error/>", 400)


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    data = fetch_m3u()
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return redirect(s["direct_source"])
    return Response("Stream not found", status=404)


@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    token = get_m3u4u_token()
    return redirect(f"https://m3u4u.com/epg/{token}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
