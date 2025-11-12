import os, time, re, requests
from flask import Flask, request, redirect, jsonify, Response

app = Flask(__name__)

# ---------------- CONFIG ----------------
USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin",
}

# ✅ Default playlist for everyone except John
DEFAULT_M3U_URL = (
    "https://www.dropbox.com/scl/fi/no7lxzan1p7u2xxghtcyh/"
    "m3u4u-102864-675366-Playlist.m3u?"
    "rlkey=szo7ff13ym9niie46aovzkvtq&st=jyouomsg&dl=1"
)

# ✅ Custom playlist for John
USER_M3U_URLS = {
    "John": (
        "https://www.dropbox.com/scl/fi/h46n1fssly1ntasgg00id/"
        "m3u4u-102864-35343-MergedPlaylist.m3u?"
        "rlkey=7rgc5z8g5znxfgla17an50smz&st=ekopupn5&dl=1"
    )
}

# ✅ New Dropbox-hosted EPG
EPG_URL = (
    "https://www.dropbox.com/scl/fi/wd8xsjxcb2clpf3bh1mo5/"
    "m3u4u-102864-670937-EPG.xml?"
    "rlkey=lhz7pzjqeg96z81z7v7zt7qph&st=ulrkulrk&dl=1"
)

CACHE_TTL = 86400  # 24 hours
_m3u_cache = {}

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# ---------------- HELPERS ----------------
def valid_user(u, p):
    return u in USERS and USERS[u] == p

def get_m3u_url_for_user(u):
    return USER_M3U_URLS.get(u, DEFAULT_M3U_URL)

def parse_m3u(txt):
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    streams, cat_map, next_cat_id, stream_id = [], {}, 1, 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))
            name = lines[i].split(",", 1)[1].strip() if "," in lines[i] else attrs.get("tvg-name", "Channel")
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"): j += 1
            url = lines[j] if j < len(lines) else ""
            group = attrs.get("group-title", "Uncategorised")
            logo, epg = attrs.get("tvg-logo", ""), attrs.get("tvg-id", "")
            if group not in cat_map:
                cat_map[group] = next_cat_id
                next_cat_id += 1
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
                "tv_archive_duration": 0,
            })
            stream_id += 1
            i = j
        else:
            i += 1
    categories = [{"category_id": str(v), "category_name": k, "parent_id": 0} for k, v in cat_map.items()]
    return {"categories": categories, "streams": streams}

def fetch_m3u_for_user(username):
    """Fetch playlist per user (independent cache)."""
    now = time.time()
    entry = _m3u_cache.get(username)
    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["parsed"]

    url = get_m3u_url_for_user(username)
    print(f"[INFO] Fetching playlist for {username}...")
    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=25)
        r.raise_for_status()
        parsed = parse_m3u(r.text)
        _m3u_cache[username] = {
            "parsed": parsed,
            "ts": now,
            "last_fetch": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        print(f"[OK] Cached {len(parsed['streams'])} streams for {username}")
        return parsed
    except Exception as e:
        print(f"[ERROR] Fetch failed for {username}: {e}")
        return {"categories": [], "streams": []}

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return (
        "✅ Xtream Bridge (Dropbox multi-user, isolated cache)<br>"
        "<a href='/refresh'>🔄 Force refresh</a> | "
        "<a href='/whoami?username=main&password=admin'>🧭 WhoAmI Test</a>"
    )

@app.route("/refresh")
def refresh():
    _m3u_cache.clear()
    for u in USERS.keys():
        fetch_m3u_for_user(u)
    return "✅ Cache cleared and all playlists refreshed."

@app.route("/whoami")
def whoami():
    """Show which playlist this user gets and first 2 channels."""
    u, p = request.args.get("username", ""), request.args.get("password", "")
    if not valid_user(u, p):
        return jsonify({"error": "invalid credentials"}), 403

    entry = _m3u_cache.get(u)
    playlist_url = get_m3u_url_for_user(u)
    last_fetch = entry["last_fetch"] if entry else "not cached"
    streams = entry["parsed"]["streams"] if entry else []
    first_two = [s["name"] for s in streams[:2]] if streams else []

    return jsonify({
        "username": u,
        "playlist_url": playlist_url,
        "cached_streams": len(streams),
        "last_fetch": last_fetch,
        "source": "custom" if u in USER_M3U_URLS else "default",
        "first_channels": first_two
    })

@app.route("/get.php")
def getphp():
    u, p = request.args.get("username", ""), request.args.get("password", "")
    if not valid_user(u, p):
        return Response("Invalid credentials", 403)
    return redirect(get_m3u_url_for_user(u))

@app.route("/player_api.php")
def api():
    u, p = request.args.get("username", ""), request.args.get("password", "")
    a = request.args.get("action", "")
    if not valid_user(u, p):
        return jsonify({"error": "invalid credentials"}), 403

    data = fetch_m3u_for_user(u)
    if a == "get_live_streams":
        return jsonify(data["streams"])
    if a == "get_live_categories":
        return jsonify(data["categories"])
    return jsonify({"user": u, "action": a})

@app.route("/live/<u>/<p>/<int:id>.<ext>")
def live(u, p, id, ext):
    if not valid_user(u, p):
        return Response("Invalid credentials", 403)
    data = fetch_m3u_for_user(u)
    for s in data["streams"]:
        if s["stream_id"] == id:
            return redirect(s["direct_source"])
    return Response("Not found", 404)

@app.route("/xmltv.php")
def xml():
    """Redirect to Dropbox-hosted EPG"""
    u, p = request.args.get("username", ""), request.args.get("password", "")
    if not valid_user(u, p):
        return Response("Invalid credentials", 403)
    return redirect(EPG_URL)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
