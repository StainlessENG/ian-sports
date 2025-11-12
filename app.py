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
    "John": "Sidford2025",   # capital J
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Default playlist for everyone EXCEPT John
DEFAULT_M3U_URL = (
    "https://www.dropbox.com/scl/fi/xz0966ignzhvfu4k6b9if/"
    "m3u4u-102864-674859-Playlist.m3u?"
    "rlkey=eomxtmihnxvq9hpd1ic41bfgb&st=9h1js2c3&dl=1"
)

# Custom playlist for John
USER_M3U_URLS = {
    "John": (
        "https://www.dropbox.com/scl/fi/h46n1fssly1ntasgg00id/"
        "m3u4u-102864-35343-MergedPlaylist.m3u?"
        "rlkey=7rgc5z8g5znxfgla17an50smz&st=ekopupn5&dl=1"
    )
}

EPG_URL = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"

CACHE_TTL = 86400
_m3u_cache = {}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ---------------- HELPERS ----------------

def valid_user(username, password):
    return username in USERS and USERS[username] == password


def get_m3u_url_for_user(username):
    return USER_M3U_URLS.get(username, DEFAULT_M3U_URL)


def wants_json():
    fmt = request.values.get("output", "").lower()
    if fmt == "json":
        return True
    if fmt in ["xml", "m3u8", "ts"]:
        return False

    ua = request.headers.get("User-Agent", "").lower()
    accept = request.headers.get("Accept", "").lower()

    if "smarters" in ua:
        return True
    if "okhttp" in ua:
        return True
    if "json" in accept:
        return True
    if "xml" in accept:
        return False

    return True


def fetch_m3u(url, username=""):
    now = time.time()
    entry = _m3u_cache.get(url)

    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["parsed"]

    try:
        print(f"[INFO] Fetching: {username or url}")
        r = requests.get(url, headers=UA_HEADERS, timeout=25)
        r.raise_for_status()
        parsed = parse_m3u(r.text)

        _m3u_cache[url] = {
            "parsed": parsed,
            "ts": now,
            "last_fetch": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }

        return parsed

    except Exception as e:
        print(f"[ERROR] Fetch failed: {username} => {e}")
        return {"categories": [], "streams": []}


def fetch_m3u_for_user(username):
    return fetch_m3u(get_m3u_url_for_user(username), username)


def parse_m3u(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams, cat_map = [], {}
    stream_id = 1
    next_cat = 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')

    i = 0
    while i < len(lines):

        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))

            name = lines[i].split(",", 1)[1].strip()
            group = attrs.get("group-title", "Uncategorised")
            logo = attrs.get("tvg-logo", "")
            epg = attrs.get("tvg-id", "")

            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1

            url = lines[j] if j < len(lines) else ""

            if group not in cat_map:
                cat_map[group] = next_cat
                next_cat += 1

            streams.append({
                "stream_id": stream_id,
                "num": stream_id,
                "name": name,
                "stream_type": "live",
                "stream_icon": logo,
                "epg_channel_id": epg,
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

    categories = [
        {"category_id": str(v), "category_name": k, "parent_id": 0}
        for k, v in cat_map.items()
    ]

    return {"categories": categories, "streams": streams}

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return "Xtream Bridge OK"


@app.route("/player_api.php")
def player_api():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    action = request.args.get("action", "")

    use_json = wants_json()

    if not valid_user(username, password):
        res = {"user_info": {"auth": 0, "status": "Disabled"}}
        return jsonify(res) if use_json else Response("<error>Invalid</error>", 403)

    if action == "":
        info = {
            "server_info": {
                "url": request.host,
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "timestamp_now": int(time.time())
            },
            "user_info": {
                "username": username,
                "auth": 1,
                "status": "Active"
            }
        }
        return jsonify(info)

    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        return jsonify(cats)

    if action == "get_live_streams":
        streams = fetch_m3u_for_user(username)["streams"]
        return jsonify(streams)

    return jsonify({"error": "unknown action"})


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live(username, password, stream_id, ext):
    if not valid_user(username, password):
        return Response("Invalid", 403)

    data = fetch_m3u_for_user(username)
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return redirect(s["direct_source"])

    return Response("Not found", 404)


@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    if not valid_user(username, password):
        return Response("Invalid", 403)
    return redirect(EPG_URL)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
