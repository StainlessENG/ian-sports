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
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Dropbox-hosted M3U (make sure dl=1 for direct)
M3U_URL = "https://www.dropbox.com/scl/fi/1u7zsewtv22z4qxjsbuol/m3u4u-102864-675347-Playlist.m3u?rlkey=k20q8mtc7kyc5awdqonlngvt7&st=e90xbhth&dl=1"

# EPG (use your working source)
EPG_URL = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"

CACHE_TTL = 86400  # 24 hours
# ----------------------------------------

_m3u_cache = {"ts": 0, "parsed": None, "last_fetch_time": "Never"}


def valid_user(username, password):
    return username in USERS and USERS[username] == password


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


def fetch_m3u():
    now = time.time()
    if _m3u_cache["parsed"] and now - _m3u_cache["ts"] < CACHE_TTL:
        return _m3u_cache["parsed"]

    try:
        print("[INFO] Fetching fresh M3U from Dropbox...")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(M3U_URL, headers=headers, timeout=25)
        resp.raise_for_status()

        parsed = parse_m3u(resp.text)
        _m3u_cache["parsed"] = parsed
        _m3u_cache["ts"] = now
        _m3u_cache["last_fetch_time"] = time.strftime(
            "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
        )
        print(f"[INFO] ✅ Cached playlist updated at {_m3u_cache['last_fetch_time']}")
        return parsed
    except Exception as e:
        print(f"[ERROR] Unable to fetch playlist: {e}")
        return _m3u_cache["parsed"] or {"categories": [], "streams": []}


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


@app.route("/")
def index():
    count = len(_m3u_cache["parsed"]["streams"]) if _m3u_cache["parsed"] else 0
    return (
        f"✅ Xtream Bridge via Dropbox<br>"
        f"Cache TTL: 24h<br>"
        f"Last Fetch: {_m3u_cache['last_fetch_time']}<br>"
        f"Streams Cached: {count}"
    )


@app.route("/get.php")
def get_m3u():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(M3U_URL)


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
        cats = fetch_m3u()["categories"]
        return jsonify(cats) if use_json else Response(tostring(Element("categories")), content_type="text/xml")

    if action == "get_live_streams":
        data = fetch_m3u()
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


# Redirect-only live route (no proxying)
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
    return redirect(EPG_URL)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
