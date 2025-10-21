
import os
import time
import re
import requests
from flask import Flask, request, Response, jsonify, redirect, abort

# ==============================
# Lightweight Xtream Front-End
# ==============================
# - Pulls M3U from m3u4u (or another M3U source)
# - Provides Xtream-like endpoints for IPTV apps:
#     * /player_api.php        -> user_info, server_info, live streams list
#     * /get.php               -> M3U playlist (uses DIRECT source URLs)
#     * /xmltv.php             -> optional pass-through XMLTV (if EPG_URL set)
# - NO video proxying: M3U contains direct .m3u8/.ts links from the source
# - /live/<user>/<pass>/<id>  -> 302 redirect to original URL (no streaming)
#
# Env Vars (optional):
#     M3U_URL      - source playlist (default: user's m3u4u URL)
#     EPG_URL      - optional XMLTV URL to pass through
#     CACHE_TTL    - seconds to cache source playlist (default: 600)
#
# Notes:
#     * Designed for free-tier hosting: the server never moves video traffic.
#     * Keep VALID_USERS small & simple. Add/remove entries as needed.

# -------------------------------
# Config
# -------------------------------
M3U_URL = os.getenv("M3U_URL", "http://m3u4u.com/m3u/w16vy52exeax15kzn39p")
EPG_URL = os.getenv("EPG_URL")  # leave None if you don't have one
CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))  # 10 minutes default

# Keep existing users (from your original app)
VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
}

app = Flask(__name__)

# -------------------------------
# In-memory cache of parsed M3U
# -------------------------------
_cache = {
    "fetched_at": 0.0,
    "channels": [],   # list of dicts with: id, name, group, logo, url, tvg_id
    "by_id": {},      # id -> channel dict
}

M3U_EXTINF_RE = re.compile(
    r'#EXTINF:-?\d+\s*(?P<attrs>[^,]*)\s*,\s*(?P<name>.*)\s*$', re.IGNORECASE)
M3U_ATTR_RE = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')

def _http_get(url, timeout=20):
    r = requests.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def _parse_m3u(text):
    \"\"\"Parse an M3U/M3U8 text into a list of channels with metadata.\"\"\"
    lines = text.splitlines()
    channels = []
    current = None
    stream_id = 1
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(\"#EXTINF\"):
            m = M3U_EXTINF_RE.match(line)
            if not m:
                current = None
                continue
            attrs_raw = m.group(\"attrs\") or \"\"
            name = m.group(\"name\").strip()
            attrs = dict(M3U_ATTR_RE.findall(attrs_raw))
            channel = {
                \"id\": str(stream_id),
                \"name\": name or attrs.get(\"tvg-name\") or \"Unknown\",
                \"group\": attrs.get(\"group-title\", \"\") or \"\",
                \"logo\": attrs.get(\"tvg-logo\", \"\") or \"\",
                \"tvg_id\": attrs.get(\"tvg-id\", \"\") or \"\",
                \"url\": None,
            }
            current = channel
        elif line.startswith(\"#\"):
            # other tags ignored
            continue
        else:
            # This is a URL line following #EXTINF
            if current:
                current[\"url\"] = line
                channels.append(current)
                stream_id += 1
                current = None
    return channels

def _refresh_cache(force=False):
    now = time.time()
    if not force and (now - _cache[\"fetched_at\"] < CACHE_TTL) and _cache[\"channels\"]:
        return
    # Fetch and parse latest M3U
    resp = _http_get(M3U_URL)
    channels = _parse_m3u(resp.text)
    _cache[\"channels\"] = channels
    _cache[\"by_id\"] = {c[\"id\"]: c for c in channels}
    _cache[\"fetched_at\"] = now

def _auth_ok(username, password):
    return username in VALID_USERS and VALID_USERS[username] == password

def _server_info():
    return {
        \"url\": request.host_url.rstrip(\"/\"),
        \"https_port\": 443,
        \"server_protocol\": \"HTTP/1.1\",
        \"rtmp_port\": 0,
        \"time_now\": int(time.time()),
    }

def _user_info(username):
    return {
        \"username\": username,
        \"auth\": 1,
        \"status\": \"Active\",
        \"max_connections\": 1,   # adjust if desired
        \"is_trial\": 0,
        \"exp_date\": None,
        \"active_cons\": 0,
    }

# -------------------------------
# Routes
# -------------------------------
@app.route(\"/\")
def index():
    return jsonify({
        \"status\": \"ok\",
        \"message\": \"Lightweight Xtream front-end (direct URLs, no proxy).\",\
        \"source\": M3U_URL,
        \"cached_channels\": len(_cache[\"channels\"]),
        \"cache_age_sec\": int(time.time() - _cache[\"fetched_at\"]) if _cache[\"fetched_at\"] else None
    })

@app.route(\"/player_api.php\", methods=[\"GET\", \"POST\"])
def player_api():
    # Support GET or POST forms
    username = request.values.get(\"username\", \"\")
    password = request.values.get(\"password\", \"\")
    action = request.values.get(\"action\")

    if not _auth_ok(username, password):
        # Xtream-style unauth
        return jsonify({\"user_info\": {\"auth\": 0}, \"server_info\": _server_info()}), 200

    # Ensure channels in cache
    _refresh_cache()

    if not action:
        # Return basic user/server info; many apps request this first
        return jsonify({
            \"user_info\": _user_info(username),
            \"server_info\": _server_info(),
        })

    if action == \"get_live_streams\":
        result = []
        for ch in _cache[\"channels\"]:
            result.append({
                \"num\": int(ch[\"id\"]),
                \"name\": ch[\"name\"],
                \"stream_type\": \"live\",
                \"stream_id\": int(ch[\"id\"]),
                \"stream_icon\": ch[\"logo\"],
                \"category_id\": ch[\"group\"] or \"0\",
                \"tvg_id\": ch[\"tvg_id\"],
            })
        return jsonify(result)

    if action in (\"get_vod_streams\", \"get_series\", \"get_vod_categories\", \"get_live_categories\", \"get_series_categories\"):
        # Minimal empty responses keep clients happy
        return jsonify([])

    if action == \"get_user_info\":
        return jsonify(_user_info(username))

    # Fallback basic info
    return jsonify({
        \"user_info\": _user_info(username),
        \"server_info\": _server_info(),
    })

@app.route(\"/get.php\")
def get_php():
    \"\"\"Produce an M3U playlist for the authenticated user.
    IMPORTANT: The stream URLs are the ORIGINAL source URLs (no proxy).\"\"\"
    username = request.args.get(\"username\", \"\")
    password = request.args.get(\"password\", \"\")
    output = request.args.get(\"output\", \"m3u8\")  # ignored; we keep direct URLs

    if not _auth_ok(username, password):
        return Response(\"#EXTM3U\\n\", mimetype=\"application/x-mpegURL\")

    _refresh_cache()

    lines = [\"#EXTM3U\"]
    for ch in _cache[\"channels\"]:
        attrs = []
        if ch[\"tvg_id\"]:
            attrs.append(f'tvg-id=\"{ch[\"tvg_id\"]}\"')
        if ch[\"logo\"]:
            attrs.append(f'tvg-logo=\"{ch[\"logo\"]}\"')
        if ch[\"group\"]:
            attrs.append(f'group-title=\"{ch[\"group\"]}\"')
        attr_str = \" \".join(attrs)
        lines.append(f'#EXTINF:-1 {attr_str},{ch[\"name\"]}')
        # DIRECT original URL
        lines.append(ch[\"url\"])

    body = \"\\n\".join(lines) + \"\\n\"
    return Response(body, mimetype=\"application/x-mpegURL\")

@app.route(\"/xmltv.php\")
def xmltv():
    \"\"\"Optional: pass-through XMLTV if EPG_URL is configured.
    Otherwise return 204 No Content.\"\"\"
    if not EPG_URL:
        return (\"\", 204)
    try:
        r = requests.get(EPG_URL, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return Response(r.content, mimetype=\"application/xml\")
    except Exception as e:
        return Response(f\"<!-- EPG fetch error: {e} -->\", mimetype=\"application/xml\")

@app.route(\"/live/<username>/<password>/<stream_id>\")
@app.route(\"/live/<username>/<password>/<stream_id>.<ext>\")
def live_redirect(username, password, stream_id, ext=None):
    \"\"\"Some clients will still try to hit /live/.../id.m3u8 or .ts.
    We do a 302 redirect to the ORIGINAL source URL. No streaming here.\"\"\"
    if not _auth_ok(username, password):
        abort(401)
    _refresh_cache()
    ch = _cache[\"by_id\"].get(str(stream_id))
    if not ch:
        abort(404)
    # 302 redirect to original
    return redirect(ch[\"url\"], code=302)

@app.route(\"/healthz\")
def healthz():
    return \"ok\", 200

if __name__ == \"__main__\":
    port = int(os.getenv(\"PORT\", \"8000\"))
    app.run(host=\"0.0.0.0\", port=port)
