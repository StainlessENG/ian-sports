import os
import time
import re
import requests
from flask import Flask, request, redirect, jsonify, Response
from xml.etree.ElementTree import Element, SubElement, tostring

app = Flask(__name__)

# ---------------- CONFIG ----------------
USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",  # capital J
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# ✅ Default M3U for everyone EXCEPT John
DEFAULT_M3U_URL = (
    "https://www.dropbox.com/scl/fi/xz0966ignzhvfu4k6b9if/"
    "m3u4u-102864-674859-Playlist.m3u?"
    "rlkey=eomxtmihnxvq9hpd1ic41bfgb&st=9h1js2c3&dl=1"
)

# ✅ Custom M3U for John (capital J)
USER_M3U_URLS = {
    "John": (
        "https://www.dropbox.com/scl/fi/h46n1fssly1ntasgg00id/"
        "m3u4u-102864-35343-MergedPlaylist.m3u?"
        "rlkey=7rgc5z8g5znxfgla17an50smz&st=ekopupn5&dl=1"
    )
}

EPG_URL = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"
CACHE_TTL = 86400  # 24 hours
_m3u_cache = {}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


# -------- Helpers --------
def valid_user(username, password):
    return username in USERS and USERS[username] == password


def get_m3u_url_for_user(username):
    """Return per-user playlist or default."""
    return USER_M3U_URLS.get(username, DEFAULT_M3U_URL)


def wants_json():
    accept = request.headers.get("Accept", "").lower()
    ua = request.headers.get("User-Agent", "").lower()
    if "smarters" in ua or "okhttp" in ua:
        return True
    if "xml" in accept:
        return False
    fmt = request.values.get("output", "").lower()
    if fmt == "json":
        return True
    if fmt in ["xml", "m3u8", "ts"]:
        return False
    return True


def fetch_m3u(url, username=""):
    """Fetch and parse playlist (with cache)."""
    now = time.time()
    entry = _m3u_cache.get(url)
    if entry and entry.get("parsed") and now - entry.get("ts", 0) < CACHE_TTL:
        return entry["parsed"]

    try:
        print(f"[INFO] Fetching fresh M3U for '{username or url}'...")
        resp = requests.get(url, headers=UA_HEADERS, timeout=25)
        resp.raise_for_status()
        parsed = parse_m3u(resp.text)
        _m3u_cache[url] = {
            "ts": now,
            "parsed": parsed,
            "last_fetch_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        print(f"[INFO] ✅ Cached playlist for '{username or url}' at {_m3u_cache[url]['last_fetch_time']}")
        return parsed
    except Exception as e:
        print(f"[ERROR] Failed to fetch playlist for '{username or url}': {e}")
        return (entry and entry.get("parsed")) or {"categories": [], "streams": []}


def fetch_m3u_for_user(username):
    return fetch_m3u(get_m3u_url_for_user(username), username)


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
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            url = lines[j].strip() if j < len(lines) else ""
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
                "tv_archive_duration": 0,
            })
            stream_id += 1
            i = j
        else:
            i += 1
    categories = [{"category_id": str(cid), "category_name": n, "parent_id": 0}
                  for n, cid in sorted(cat_map.items(), key=lambda x: x[1])]
    return {"categories": categories, "streams": streams}


# -------- Routes --------
@app.route("/")
def index():
    default = _m3u_cache.get(DEFAULT_M3U_URL, {})
    john = _m3u_cache.get(USER_M3U_URLS.get("John", ""), {})
    return (
        f"✅ Xtream Bridge via Dropbox (multi-user)<br>"
        f"<b>Default</b> — Last Fetch: {default.get('last_fetch_time','Never')} "
        f"| Streams: {len(default.get('parsed', {}).get('streams', []))}<br>"
        f"<b>John</b> — Last Fetch: {john.get('last_fetch_time','Never')} "
        f"| Streams: {len(john.get('parsed', {}).get('streams', []))}<br><br>"
        f"<a href='/debug'>🔍 Debug what each user sees</a><br>"
        f"<a href='/refresh'>🔄 Force refresh playlists</a><br>"
        f"<a href='/whoami?username=main&password=admin'>🧭 Try /whoami test</a>"
    )


@app.route("/debug")
def debug_info():
    """Show which URLs and files are currently mapped and cached."""
    info = []
    for user in USERS.keys():
        url = get_m3u_url_for_user(user)
        try:
            text = ""
            if url in _m3u_cache and "parsed" in _m3u_cache[url]:
                text = f"(cached: {len(_m3u_cache[url]['parsed']['streams'])} streams)"
            else:
                resp = requests.get(url, headers=UA_HEADERS, timeout=10)
                resp.raise_for_status()
                lines = resp.text.splitlines()[:5]
                text = "<br>".join(lines)
            info.append(f"<b>{user}</b> → {url}<br>{text}<br><hr>")
        except Exception as e:
            info.append(f"<b>{user}</b> → {url}<br>❌ Error: {e}<hr>")
    return "<h3>🔍 Current User-to-Playlist Mapping</h3>" + "".join(info)


@app.route("/refresh")
def refresh_all():
    """Force clear and re-fetch all playlists."""
    print("[INFO] 🔄 Manual full refresh triggered...")
    _m3u_cache.clear()
    fetch_m3u(DEFAULT_M3U_URL, "Default")
    for user, url in USER_M3U_URLS.items():
        fetch_m3u(url, user)
    return "✅ All playlists forcibly refreshed and re-cached."


@app.route("/whoami")
def whoami():
    """Show which playlist and cache info this user gets."""
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return jsonify({
            "status": "error",
            "message": "Invalid credentials"
        }), 403

    url = get_m3u_url_for_user(username)
    cache_entry = _m3u_cache.get(url, {})
    last_fetch = cache_entry.get("last_fetch_time", "Not cached yet")
    stream_count = len(cache_entry.get("parsed", {}).get("streams", [])) if "parsed" in cache_entry else 0

    return jsonify({
        "username": username,
        "playlist_url": url,
        "cached_streams": stream_count,
        "last_fetch_time": last_fetch,
        "source": "USER_M3U_URLS" if username in USER_M3U_URLS else "DEFAULT_M3U_URL"
    })


@app.route("/get.php")
def get_m3u():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(get_m3u_url_for_user(username))


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
                "allowed_output_formats": ["m3u8", "ts"],
            },
            "server_info": {
                "url": request.host.split(":")[0],
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "1935",
                "timezone": "UTC",
                "timestamp_now": int(time.time()),
                "time_now": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        return jsonify(info) if use_json else Response("<status>Active</status>", content_type="text/xml")

    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        return jsonify(cats) if use_json else Response(tostring(Element("categories")), content_type="text/xml")

    if action == "get_live_streams":
        data = fetch_m3u_for_user(username)
        cat_filter = request.values.get("category_id")
        result = [s for s in data["streams"] if not cat_filter or str(s["category_id"]) == str(cat_filter)]
        return jsonify(result) if use_json else Response(tostring(Element("channels")), content_type="text/xml")

    if action in [
        "get_vod_categories", "get_vod_streams", "get_series_categories",
        "get_series", "get_series_info", "get_vod_info",
        "get_short_epg", "get_simple_data_table"
    ]:
        return jsonify([]) if use_json else Response("<empty/>", content_type="text/xml")

    return jsonify({"error": "action not handled", "action": action}) if use_json else Response("<error/>", 400)


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    data = fetch_m3u_for_user(username)
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return redirect(s["direct_source"])
    return Response("Stream not found", status=404)


@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(EPG_URL)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
