
import os
import time
import re
import requests
from flask import Flask, request, Response, jsonify, redirect, abort

M3U_URL = os.getenv("M3U_URL", "http://m3u4u.com/m3u/w16vy52exeax15kzn39p")
EPG_URL = os.getenv("EPG_URL", "http://m3u4u.com/epg/w16vy52exeax15kzn39p")
CACHE_TTL = int(os.getenv("CACHE_TTL", "1800"))

VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
}

app = Flask(__name__)

_cache = {
    "fetched_at": 0.0,
    "channels": [],
    "by_id": {},
    "categories": [],
    "cat_index": {},
}

M3U_EXTINF_RE = re.compile(r'#EXTINF:-?\d+\s*(?P<attrs>[^,]*)\s*,\s*(?P<name>.*)\s*$', re.IGNORECASE)
M3U_ATTR_RE = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')

def _http_get(url, timeout=25):
    r = requests.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def _parse_m3u(text):
    lines = text.splitlines()
    channels = []
    current = None
    stream_id = 1
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            m = M3U_EXTINF_RE.match(line)
            if not m:
                current = None
                continue
            attrs_raw = m.group("attrs") or ""
            name = (m.group("name") or "").strip()
            attrs = dict(M3U_ATTR_RE.findall(attrs_raw))
            current = {
                "id": str(stream_id),
                "name": name or attrs.get("tvg-name") or "Unknown Channel",
                "group": attrs.get("group-title", "") or "Uncategorized",
                "logo": attrs.get("tvg-logo", "") or "",
                "tvg_id": attrs.get("tvg-id", "") or "",
                "url": None,
            }
        elif line.startswith("#"):
            continue
        else:
            if current:
                current["url"] = line
                channels.append(current)
                stream_id += 1
                current = None
    return channels

def _build_categories(channels):
    cat_names = []
    for ch in channels:
        g = ch.get("group") or "Uncategorized"
        if g not in cat_names:
            cat_names.append(g)
    categories = []
    cat_index = {}
    for i, name in enumerate(cat_names, start=1):
        cid = str(i)
        categories.append({"category_id": cid, "category_name": name, "parent_id": 0})
        cat_index[name] = cid
    return categories, cat_index

def _refresh_cache(force=False):
    now = time.time()
    if not force and _cache["channels"] and (now - _cache["fetched_at"] < CACHE_TTL):
        return
    resp = _http_get(M3U_URL)
    channels = _parse_m3u(resp.text)
    categories, cat_index = _build_categories(channels)
    for ch in channels:
        ch["category_id"] = cat_index.get(ch.get("group") or "Uncategorized", "0")
    _cache["channels"] = channels
    _cache["by_id"] = {c["id"]: c for c in channels}
    _cache["categories"] = categories
    _cache["cat_index"] = cat_index
    _cache["fetched_at"] = now

def _auth_ok(username, password):
    return username in VALID_USERS and VALID_USERS[username] == password

def _server_info():
    return {
        "url": request.host_url.rstrip("/"),
        "https_port": "443",
        "port": "443",
        "server_protocol": "https",
        "rtmp_port": "1935",
        "timezone": "UTC",
        "time_now": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "timestamp_now": str(int(time.time())),
    }

def _user_info(username):
    return {
        "username": username,
        "password": VALID_USERS.get(username, ""),
        "message": "",
        "auth": 1,
        "status": "Active",
        "max_connections": "2",
        "is_trial": "0",
        "created_at": "1609459200",
        "exp_date": "1780185600",
        "active_cons": "0",
        "allowed_output_formats": ["m3u8", "ts"],
    }

@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "source": M3U_URL,
        "epg": EPG_URL,
        "cached_channels": len(_cache["channels"]),
        "cache_age_seconds": int(time.time() - _cache["fetched_at"]) if _cache["fetched_at"] else None,
    })

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action")

    if not _auth_ok(username, password):
        return jsonify({"user_info": {"auth": 0}, "server_info": _server_info()})

    _refresh_cache()

    if not action:
        return jsonify({"user_info": _user_info(username), "server_info": _server_info()})

    if action == "get_user_info":
        return jsonify(_user_info(username))

    if action == "get_live_streams":
        streams = []
        for ch in _cache["channels"]:
            streams.append({
                "num": int(ch["id"]),
                "name": ch["name"],
                "stream_type": "live",
                "stream_id": int(ch["id"]),
                "stream_icon": ch["logo"],
                "category_id": str(ch.get("category_id") or "0"),
                "added": "0",
                "is_adult": "0",
                "tvg_id": ch["tvg_id"],
                "custom_sid": "",
                "direct_source": ch["url"],
            })
        return jsonify(streams)

    if action == "get_live_categories":
        return jsonify(_cache["categories"])

    if action in ("get_vod_streams", "get_series"):
        return jsonify([])

    if action in ("get_vod_categories", "get_series_categories"):
        return jsonify([{"category_id": "1", "category_name": "VOD", "parent_id": 0}])

    return jsonify({"user_info": _user_info(username), "server_info": _server_info()})

@app.route("/get.php")
def get_php():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    _ = request.args.get("output", "m3u8")

    if not _auth_ok(username, password):
        return Response("#EXTM3U\n", mimetype="application/x-mpegURL")

    _refresh_cache()

    lines = ["#EXTM3U"]
    for ch in _cache["channels"]:
        attrs = []
        if ch["tvg_id"]:
            attrs.append(f'tvg-id="{ch["tvg_id"]}"')
        if ch["logo"]:
            attrs.append(f'tvg-logo="{ch["logo"]}"')
        if ch["group"]:
            attrs.append(f'group-title="{ch["group"]}"')
        attr_str = " ".join(attrs)
        lines.append(f'#EXTINF:-1 {attr_str},{ch["name"]}')
        lines.append(ch["url"])
    body = "\n".join(lines) + "\n"
    return Response(body, mimetype="application/x-mpegURL")

@app.route("/xmltv.php")
def xmltv():
    if not EPG_URL:
        return ("", 204)
    try:
        r = _http_get(EPG_URL, timeout=30)
        return Response(r.content, mimetype="application/xml")
    except Exception as e:
        return Response(f"<!-- EPG fetch error: {e} -->", mimetype="application/xml")

@app.route("/live/<username>/<password>/<stream_id>")
@app.route("/live/<username>/<password>/<stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext=None):
    if not _auth_ok(username, password):
        abort(401)
    _refresh_cache()
    ch = _cache["by_id"].get(str(stream_id))
    if not ch:
        abort(404)
    return redirect(ch["url"], code=302)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
