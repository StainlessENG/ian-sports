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
    "john": "pass123",            # existing 'john'
    "John": "Sidford2025",        # NEW: capital-J John
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Default M3U for everyone (make sure dl=1)
DEFAULT_M3U_URL = (
    "https://www.dropbox.com/scl/fi/1u7zsewtv22z4qxjsbuol/"
    "m3u4u-102864-675347-Playlist.m3u?rlkey=k20q8mtc7kyc5awdqonlngvt7"
    "&st=e90xbhth&dl=1"
)

# Per-user M3U overrides
USER_M3U_URLS = {
    # NEW: John (capital J) uses a different playlist
    "John": "https://www.dropbox.com/scl/fi/h46n1fssly1ntasgg00id/"
            "m3u4u-102864-35343-MergedPlaylist.m3u?rlkey=7rgc5z8g5znxfgla17an50smz"
            "&st=un3tsyuc&dl=1"
}

# EPG (same for all unless you add per-user later)
EPG_URL = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"

# Cache TTL: 24 hours
CACHE_TTL = 86400
# ----------------------------------------

# Cache keyed by source URL so each playlist is cached independently
# Example: _m3u_cache[url] = {"ts": epoch_seconds, "parsed": {...}, "last_fetch_time": "..."}
_m3u_cache = {}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


# -------- Helper functions --------
def valid_user(username, password):
    return username in USERS and USERS[username] == password


def get_m3u_url_for_user(username: str) -> str:
    """Return the per-user M3U URL or the default."""
    return USER_M3U_URLS.get(username, DEFAULT_M3U_URL)


def wants_json():
    accept = request.headers.get("Accept", "").lower()
    user_agent = request.headers.get("User-Agent", "").lower()
    if "smarters" in user_agent or "okhttp" in user_agent:
        return True
    if "xml" in accept:
        return False
    fmt = request.values.get("output", "").lower()
    if fmt == "json":
        return True
    if fmt in ["xml", "m3u8", "ts"]:
        return False
    return True


def fetch_m3u_for_user(username: str):
    """
    Fetch and cache the M3U for a specific user (per-URL cache).
    """
    url = get_m3u_url_for_user(username)
    now = time.time()
    entry = _m3u_cache.get(url)

    if entry and entry.get("parsed") and now - entry.get("ts", 0) < CACHE_TTL:
        return entry["parsed"]

    try:
        print(f"[INFO] Fetching fresh M3U from Dropbox for user '{username}'...")
        resp = requests.get(url, headers=UA_HEADERS, timeout=25)
        resp.raise_for_status()

        parsed = parse_m3u(resp.text)
        _m3u_cache[url] = {
            "ts": now,
            "parsed": parsed,
            "last_fetch_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        print(f"[INFO] ✅ Cached playlist for '{username}' updated at {_m3u_cache[url]['last_fetch_time']}")
        return parsed

    except Exception as e:
        print(f"[ERROR] Unable to fetch playlist for '{username}': {e}")
        # Fallback to last known parsed for this URL if exists
        return (entry and entry.get("parsed")) or {"categories": [], "streams": []}


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
    # Show some quick status for default URL
    default = _m3u_cache.get(DEFAULT_M3U_URL, {})
    default_count = len(default.get("parsed", {}).get("streams", [])) if default.get("parsed") else 0
    default_last = default.get("last_fetch_time", "Never")

    # Also show John’s status if present
    john_url = USER_M3U_URLS.get("John")
    john = _m3u_cache.get(john_url, {}) if john_url else {}
    john_count = len(john.get("parsed", {}).get("streams", [])) if john.get("parsed") else 0
    john_last = john.get("last_fetch_time", "Never")

    return (
        "✅ Xtream Bridge via Dropbox (per-user playlists)<br>"
        f"<b>Default</b> — Last Fetch: {default_last} | Streams: {default_count}<br>"
        f"<b>John</b> — Last Fetch: {john_last} | Streams: {john_count}"
    )


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
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": request.host.split(":")[0],
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


# Redirect-only live route (kept as before)
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
    # Same EPG for all users (adjust here if you add per-user later)
    return redirect(EPG_URL)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
