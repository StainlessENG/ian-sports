import os
import time
import re
import requests
from flask import Flask, request, redirect, jsonify, Response

app = Flask(__name__)

# ---------------- CONFIG ----------------

USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",   # John gets DEFAULT feed
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin",         # main gets SPECIAL feed
}

# M3U4U FEEDS (24h limit!)
DEFAULT_M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
DEFAULT_EPG_URL = "http://m3u4u.com/xml/jwmzn1w282ukvxw4n721"

MAIN_M3U_URL = "http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j"
MAIN_EPG_URL = "http://m3u4u.com/xml/p87vnr8dzdu4w2q6n41j"

# Per-user playlist mapping (John uses default feed)
USER_M3U_URLS = {
    "main": MAIN_M3U_URL,
}

USER_EPG_URLS = {
    "main": MAIN_EPG_URL,
}

# 24h in seconds. We will NEVER call m3u4u more often than this.
CACHE_TTL = 86400

# In-memory caches. NOTE: if the server restarts often, you could
# add simple file-based persistence, but this is already safe per process.
_m3u_cache = {}   # url -> {parsed, raw, ts, last_error}
_epg_cache = {}   # url -> {xml, ts, last_error}

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


def get_m3u_url_for_user(username: str) -> str:
    """
    Return per-user playlist or default.
    'main' gets special feed; everyone else (including 'John') gets default.
    """
    url = USER_M3U_URLS.get(username, DEFAULT_M3U_URL)
    print(f"[CONFIG] User '{username}' → {'SPECIAL' if username == 'main' else 'DEFAULT'} playlist")
    print(f"[CONFIG] M3U URL: {url}")
    return url


def get_epg_url_for_user(username: str) -> str:
    """
    Per-user EPG URL. 'main' gets special, others default.
    """
    url = USER_EPG_URLS.get(username, DEFAULT_EPG_URL)
    print(f"[CONFIG] User '{username}' → {'SPECIAL' if username == 'main' else 'DEFAULT'} EPG")
    print(f"[CONFIG] EPG URL: {url}")
    return url


def wants_json() -> bool:
    """
    Keep it simple and safe:
    - Only return JSON if the client explicitly asks with output=json.
    - Otherwise, ALWAYS return XML (better for IPTV Smarters).
    """
    fmt = request.values.get("output", "").lower()
    return fmt == "json"


def list_to_xml(root_tag, item_tag, data_list):
    """Convert list of dicts to XML string."""
    from xml.etree.ElementTree import Element, SubElement, tostring

    root = Element(root_tag)
    for item in data_list:
        item_elem = SubElement(root, item_tag)
        for key, val in item.items():
            child = SubElement(item_elem, key)
            child.text = "" if val is None else str(val)
    return tostring(root, encoding="unicode")


def parse_m3u(text: str):
    """
    Parse raw M3U into categories + streams.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams, cat_map = [], {}
    stream_id = 1
    next_cat = 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')

    epg_url = None
    if lines and lines[0].startswith("#EXTM3U"):
        header_attrs = dict(attr_re.findall(lines[0]))
        epg_url = header_attrs.get("url-tvg") or header_attrs.get("x-tvg-url")

    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))
            name = lines[i].split(",", 1)[1].strip() if "," in lines[i] else "Channel"
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
                "tv_archive_duration": 0,
                "custom_sid": "",
                "tv_archive_start": "",
                "tv_archive_stop": "",
                "container_extension": "m3u8" if ".m3u8" in url else "ts",
            })

            stream_id += 1
            i = j
        else:
            i += 1

    categories = [
        {"category_id": str(v), "category_name": k, "parent_id": 0}
        for k, v in cat_map.items()
    ]

    return {"categories": categories, "streams": streams, "epg_url": epg_url}


def fetch_m3u(url: str, username: str = ""):
    """
    Fetch and parse M3U from m3u4u.
    STRICT 24-HOUR PROTECTION:
      - At most ONE network call per URL every CACHE_TTL seconds.
      - Even if the call fails, we update ts so we don't hammer m3u4u.
    """
    now = time.time()
    entry = _m3u_cache.get(url)

    if entry and now - entry["ts"] < CACHE_TTL:
        # Cached and within 24h → DO NOT call m3u4u again.
        return entry["parsed"]

    attempt_time = now
    print(f"[M3U] Fetching for '{username or url}' (url={url})")

    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=25)
        r.raise_for_status()
        raw_text = r.text
        parsed = parse_m3u(raw_text)

        _m3u_cache[url] = {
            "parsed": parsed,
            "raw": raw_text,
            "ts": attempt_time,
            "last_error": None,
            "last_fetch_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time)),
        }

        print(f"[M3U] OK: {len(parsed['streams'])} streams cached for '{username or url}'")
        return parsed

    except Exception as e:
        msg = f"[M3U] ERROR fetching '{username or url}': {e}"
        print(msg)

        # Update ts so we don't retry for another 24h,
        # even if it failed (protects against hammering m3u4u).
        if entry:
            entry["ts"] = attempt_time
            entry["last_error"] = str(e)
            entry["last_fetch_human"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time))
            return entry["parsed"]
        else:
            empty = {"categories": [], "streams": [], "epg_url": None}
            _m3u_cache[url] = {
                "parsed": empty,
                "raw": "",
                "ts": attempt_time,
                "last_error": str(e),
                "last_fetch_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time)),
            }
            return empty


def fetch_m3u_for_user(username: str):
    url = get_m3u_url_for_user(username)
    return fetch_m3u(url, username)


def fetch_epg(epg_url: str, label: str = "") -> str:
    """
    Fetch XMLTV once per 24h per URL.
    """
    now = time.time()
    entry = _epg_cache.get(epg_url)

    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["xml"]

    attempt_time = now
    print(f"[EPG] Fetching for '{label or epg_url}' (url={epg_url})")

    try:
        r = requests.get(epg_url, headers=UA_HEADERS, timeout=30)
        r.raise_for_status()
        xml = r.text

        _epg_cache[epg_url] = {
            "xml": xml,
            "ts": attempt_time,
            "last_error": None,
            "last_fetch_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time)),
        }

        print(f"[EPG] OK: Cached EPG for '{label or epg_url}'")
        return xml

    except Exception as e:
        msg = f"[EPG] ERROR fetching '{label or epg_url}': {e}"
        print(msg)

        # Avoid hammering m3u4u even on error
        if entry:
            entry["ts"] = attempt_time
            entry["last_error"] = str(e)
            entry["last_fetch_human"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time))
            return entry["xml"]
        else:
            _epg_cache[epg_url] = {
                "xml": "<tv></tv>",
                "ts": attempt_time,
                "last_error": str(e),
                "last_fetch_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(attempt_time)),
            }
            return "<tv></tv>"


# ---------------- ROUTES ----------------

@app.route("/")
def index():
    default_cache = _m3u_cache.get(DEFAULT_M3U_URL, {})
    main_cache = _m3u_cache.get(MAIN_M3U_URL, {})

    default_streams = len(default_cache.get("parsed", {}).get("streams", []))
    main_streams = len(main_cache.get("parsed", {}).get("streams", []))

    return (
        f"✅ Xtream Bridge (m3u4u Safe Mode)<br><br>"
        f"<b>Default feed:</b> {default_streams} streams<br>"
        f"<b>Main (special) feed:</b> {main_streams} streams<br><br>"
        f"<a href='/whoami?username=main&password=admin'>🧭 Test Login</a> | "
        f"<a href='/debug'>🔍 Debug Users</a> | "
        f"<a href='/test_stream/1?username=main&password=admin'>🎬 Test Stream #1</a>"
    )


@app.route("/debug")
def debug_info():
    info = ["<h2>🔍 User-to-Playlist Mapping & Cache Status</h2>"]

    info.append("<h3>Expected Assignments:</h3>")
    for user in USERS.keys():
        m3u_url = get_m3u_url_for_user(user)
        epg_url = get_epg_url_for_user(user)
        is_special = (user == "main")
        info.append(
            f"<b>{user}</b>: {'SPECIAL' if is_special else 'DEFAULT'}<br>"
            f"&nbsp;&nbsp;M3U: <small>{m3u_url}</small><br>"
            f"&nbsp;&nbsp;EPG: <small>{epg_url}</small><br><br>"
        )

    info.append("<hr><h3>M3U Cache:</h3>")
    for url, entry in _m3u_cache.items():
        streams = len(entry.get("parsed", {}).get("streams", []))
        last_fetch = entry.get("last_fetch_human", "Never")
        last_error = entry.get("last_error") or "None"
        info.append(
            f"<div style='border:1px solid #ccc;padding:8px;margin:6px 0;'>"
            f"<b>URL:</b> <small>{url}</small><br>"
            f"<b>Streams:</b> {streams}<br>"
            f"<b>Last Fetch:</b> {last_fetch}<br>"
            f"<b>Last Error:</b> <small>{last_error}</small>"
            f"</div>"
        )

    info.append("<hr><h3>EPG Cache:</h3>")
    for url, entry in _epg_cache.items():
        last_fetch = entry.get("last_fetch_human", "Never")
        last_error = entry.get("last_error") or "None"
        info.append(
            f"<div style='border:1px solid #ccc;padding:8px;margin:6px 0;'>"
            f"<b>URL:</b> <small>{url}</small><br>"
            f"<b>Last Fetch:</b> {last_fetch}<br>"
            f"<b>Last Error:</b> <small>{last_error}</small>"
            f"</div>"
        )

    info.append("<br><a href='/'>← Back to Home</a>")
    return "".join(info)


@app.route("/whoami")
def whoami():
    """Show which playlist + cache info this user gets."""
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return jsonify({"error": "Invalid credentials"}), 403

    m3u_url = get_m3u_url_for_user(username)
    cache = _m3u_cache.get(m3u_url, {})
    streams = len(cache.get("parsed", {}).get("streams", []))
    last_fetch = cache.get("last_fetch_human", "Never")

    return jsonify({
        "username": username,
        "playlist_url": m3u_url,
        "streams": streams,
        "last_fetch": last_fetch,
        "is_special": (username == "main"),
    })


@app.route("/test_stream/<int:stream_id>")
def test_stream(stream_id):
    """Debug endpoint to inspect stream URLs."""
    username = request.args.get("username", "main")
    password = request.args.get("password", "admin")

    if not valid_user(username, password):
        return "Invalid credentials", 403

    data = fetch_m3u_for_user(username)
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return f"""
            <h3>Stream #{stream_id}: {s['name']}</h3>
            <p><b>Direct URL:</b><br>
                <textarea style="width:100%;height:60px">{s['direct_source']}</textarea>
            </p>
            <p><b>Xtream URL:</b><br>
                http://{request.host}/live/{username}/{password}/{stream_id}.m3u8
            </p>
            <p><a href="{s['direct_source']}" target="_blank">Test Direct Link</a></p>
            <p><a href="/live/{username}/{password}/{stream_id}.m3u8">Test Via Proxy</a></p>
            """
    return "Stream not found", 404


@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action", "")
    use_json = wants_json()

    print(f"[API] user={username}, action={action}, json={use_json}, UA={request.headers.get('User-Agent', '')[:60]}")

    if not valid_user(username, password):
        user_info = {
            "username": username,
            "password": password,
            "message": "Invalid credentials",
            "auth": 0,
            "status": "Disabled",
        }
        if use_json:
            return jsonify({"user_info": user_info}), 403
        else:
            xml = '<?xml version="1.0" encoding="UTF-8"?><response><user_info>'
            for k, v in user_info.items():
                xml += f"<{k}>{v}</{k}>"
            xml += "</user_info></response>"
            return Response(xml, status=403, content_type="application/xml")

    # Base info (no action) - what IPTV Smarters calls first
    if action == "":
        host = request.host.split(":")[0]
        port = request.host.split(":")[1] if ":" in request.host else "80"
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
                "url": host,
                "port": port,
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "1935",
                "timezone": "UTC",
                "timestamp_now": int(time.time()),
                "time_now": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

        if use_json:
            return jsonify(info)
        else:
            xml = '<?xml version="1.0" encoding="UTF-8"?><response><user_info>'
            for k, v in info["user_info"].items():
                if isinstance(v, list):
                    v = ",".join(v)
                xml += f"<{k}>{v}</{k}>"
            xml += "</user_info><server_info>"
            for k, v in info["server_info"].items():
                xml += f"<{k}>{v}</{k}>"
            xml += "</server_info></response>"
            return Response(xml, content_type="application/xml")

    # Live categories
    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        if use_json:
            return jsonify(cats)
        else:
            xml = list_to_xml("categories", "category", cats)
            return Response('<?xml version="1.0" encoding="UTF-8"?>' + xml,
                            content_type="application/xml")

    # Live streams
    if action == "get_live_streams":
        data = fetch_m3u_for_user(username)
        cat_filter = request.values.get("category_id")
        streams = [
            s for s in data["streams"]
            if not cat_filter or str(s["category_id"]) == str(cat_filter)
        ]
        if use_json:
            return jsonify(streams)
        else:
            xml = list_to_xml("streams", "channel", streams)
            return Response('<?xml version="1.0" encoding="UTF-8"?>' + xml,
                            content_type="application/xml")

    # Account info mirror
    if action == "get_account_info":
        account_info = {
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
        }
        if use_json:
            return jsonify(account_info)
        else:
            xml = '<?xml version="1.0" encoding="UTF-8"?><user_info>'
            for k, v in account_info.items():
                xml += f"<{k}>{v}</{k}>"
            xml += "</user_info>"
            return Response(xml, content_type="application/xml")

    # Not implemented VOD/Series – return empty safely
    if action in [
        "get_vod_categories", "get_vod_streams",
        "get_series_categories", "get_series",
        "get_series_info", "get_vod_info", "get_short_epg"
    ]:
        if use_json:
            return jsonify([])
        else:
            return Response('<?xml version="1.0" encoding="UTF-8"?><response></response>',
                            content_type="application/xml")

    # Fallback
    if use_json:
        return jsonify({"error": "action not handled", "action": action})
    else:
        xml = f'<?xml version="1.0" encoding="UTF-8"?><error>Unknown action: {action}</error>'
        return Response(xml, status=400, content_type="application/xml")


# LIVE STREAM PROXY (no 302 redirect)

@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
@app.route("/live/<username>/<password>/<int:stream_id>")
@app.route("/<username>/<password>/<int:stream_id>.<ext>")
@app.route("/<username>/<password>/<int:stream_id>")
def live(username, password, stream_id, ext=None):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    data = fetch_m3u_for_user(username)
    target_stream = None
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            target_stream = s
            break

    if not target_stream:
        return Response("Stream not found", status=404)

    target_url = target_stream["direct_source"]
    requested_ext = ext or "none"
    actual_ext = "m3u8" if ".m3u8" in target_url else "ts" if ".ts" in target_url else "unknown"

    print(f"[STREAM] User: {username}, Stream: {stream_id} ({target_stream['name']})")
    print(f"[STREAM] Req ext: {requested_ext}, Actual: {actual_ext}")
    print(f"[STREAM] Proxying: {target_url}")

    try:
        upstream = requests.get(target_url, headers=UA_HEADERS, stream=True, timeout=15)
    except Exception as e:
        print(f"[STREAM] ERROR fetching upstream: {e}")
        return Response("Upstream error", status=502)

    if upstream.status_code != 200:
        print(f"[STREAM] Upstream returned {upstream.status_code}")
        return Response("Upstream error", status=upstream.status_code)

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                yield chunk
        finally:
            upstream.close()

    content_type = upstream.headers.get("Content-Type")
    if not content_type:
        content_type = "application/vnd.apple.mpegurl" if actual_ext == "m3u8" else "video/mp2t"

    return Response(generate(), content_type=content_type)


@app.route("/xmltv.php")
def xmltv():
    """
    IPTV Smarters EPG endpoint.
    We serve cached XML from m3u4u, fetched at most once every 24 hours.
    """
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    epg_url = get_epg_url_for_user(username)
    xml = fetch_epg(epg_url, label=username or "EPG")

    return Response(xml, content_type="application/xml")


@app.route("/get.php")
def get_m3u():
    """
    M3U download endpoint, e.g. for apps that want a straight playlist.
    IMPORTANT: We DO NOT redirect to m3u4u.
    We serve a cached copy so m3u4u is only hit once every 24h.
    """
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    url = get_m3u_url_for_user(username)

    # Ensure we have something in cache (will call m3u4u at most once/24h)
    fetch_m3u(url, username)
    entry = _m3u_cache.get(url, {})
    raw = entry.get("raw", "")

    if not raw:
        return Response("#EXTM3U\n", content_type="audio/x-mpegurl")

    return Response(raw, content_type="audio/x-mpegurl")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
