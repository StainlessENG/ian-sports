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

# Your GitHub M3U playlist (raw link)
M3U_URL = "https://raw.githubusercontent.com/StainlessENG/ian-sports/refs/heads/main/Main%20Playlist.m3u"
EPG_URL = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"
CACHE_TTL = 600  # seconds
# ----------------------------------------

_m3u_cache = {"ts": 0, "parsed": None}


# -------- Helper functions --------
def valid_user(username, password):
    return username in USERS and USERS[username] == password


def wants_json():
    """Detect if client wants JSON (default) or XML"""
    accept = request.headers.get('Accept', '').lower()
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Force JSON for known apps that need it
    if 'smarters' in user_agent or 'okhttp' in user_agent:
        return True
    
    # Force XML for apps that explicitly request it
    if 'xml' in accept:
        return False
    
    # Check output_format parameter (some apps use this)
    output_format = request.values.get('output', '').lower()
    if output_format == 'json':
        return True
    if output_format in ['xml', 'm3u8', 'ts']:
        return False
    
    # Default to JSON (most modern apps)
    return True


def fetch_m3u():
    now = time.time()
    if _m3u_cache["parsed"] and now - _m3u_cache["ts"] < CACHE_TTL:
        return _m3u_cache["parsed"]

    resp = requests.get(M3U_URL, timeout=15)
    resp.raise_for_status()
    text = resp.text
    parsed = parse_m3u(text)
    _m3u_cache["parsed"] = parsed
    _m3u_cache["ts"] = now
    return parsed


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


# -------- Routes --------

@app.route("/")
def index():
    return "✅ Xtream Bridge running OK (iOS + Android Compatible)"


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

    # Check credentials first
    if username not in USERS or USERS[username] != password:
        if use_json:
            return jsonify({
                "user_info": {
                    "username": username,
                    "password": password,
                    "message": "Invalid credentials",
                    "auth": 0,
                    "status": "Disabled"
                }
            })
        else:
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<user_info>
  <username>{username}</username>
  <password>{password}</password>
  <message>Invalid credentials</message>
  <auth>0</auth>
  <status>Disabled</status>
</user_info>"""
            return Response(xml, content_type="text/xml; charset=utf-8")

    # ----- LOGIN (no action) -----
    if action == "":
        if use_json:
            return jsonify({
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
            })
        else:
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<user_info>
  <username>{username}</username>
  <password>{password}</password>
  <message>Active</message>
  <auth>1</auth>
  <status>Active</status>
  <exp_date></exp_date>
  <is_trial>0</is_trial>
  <active_cons>0</active_cons>
  <created_at>1640000000</created_at>
  <max_connections>1</max_connections>
</user_info>
<server_info>
  <url>{request.host}</url>
  <port>80</port>
  <https_port>443</https_port>
  <server_protocol>http</server_protocol>
  <rtmp_port>1935</rtmp_port>
  <timestamp_now>{int(time.time())}</timestamp_now>
</server_info>"""
            return Response(xml, content_type="text/xml; charset=utf-8")

    # -------- LIVE CATEGORIES --------
    if action == "get_live_categories":
        cats = fetch_m3u()["categories"]
        if use_json:
            return jsonify(cats)
        else:
            xml_root = Element("categories")
            for c in cats:
                el = SubElement(xml_root, "category")
                for k, v in c.items():
                    SubElement(el, k).text = str(v)
            return Response(tostring(xml_root, encoding="utf-8"), 
                          content_type="application/xml; charset=utf-8")

    # -------- LIVE STREAMS --------
    if action == "get_live_streams":
        data = fetch_m3u()
        cat_filter = request.values.get("category_id")
        result = []
        for s in data["streams"]:
            if cat_filter and str(s["category_id"]) != str(cat_filter):
                continue
            result.append(s)
        
        if use_json:
            return jsonify(result)
        else:
            xml_root = Element("channels")
            for s in result:
                ch = SubElement(xml_root, "channel")
                SubElement(ch, "num").text = str(s["num"])
                SubElement(ch, "name").text = s["name"]
                SubElement(ch, "stream_type").text = s["stream_type"]
                SubElement(ch, "stream_id").text = str(s["stream_id"])
                SubElement(ch, "stream_icon").text = s["stream_icon"]
                SubElement(ch, "epg_channel_id").text = s["epg_channel_id"]
                SubElement(ch, "category_id").text = s["category_id"]
                SubElement(ch, "direct_source").text = s["direct_source"]
            return Response(tostring(xml_root, encoding="utf-8"),
                          content_type="application/xml; charset=utf-8")

    # -------- VOD CATEGORIES (empty) --------
    if action == "get_vod_categories":
        if use_json:
            return jsonify([])
        return Response("<categories/>", content_type="application/xml")

    # -------- VOD STREAMS (empty) --------
    if action == "get_vod_streams":
        if use_json:
            return jsonify([])
        return Response("<streams/>", content_type="application/xml")

    # -------- SERIES CATEGORIES (empty) --------
    if action == "get_series_categories":
        if use_json:
            return jsonify([])
        return Response("<categories/>", content_type="application/xml")

    # -------- SERIES (empty) --------
    if action == "get_series":
        if use_json:
            return jsonify([])
        return Response("<series/>", content_type="application/xml")

    # -------- SERIES INFO (empty) --------
    if action == "get_series_info":
        if use_json:
            return jsonify({})
        return Response("<info/>", content_type="application/xml")

    # -------- VOD INFO (empty) --------
    if action == "get_vod_info":
        if use_json:
            return jsonify({})
        return Response("<info/>", content_type="application/xml")

    # -------- SHORT EPG --------
    if action == "get_short_epg":
        if use_json:
            return jsonify({"epg_listings": []})
        return Response("<epg_listings/>", content_type="application/xml")

    # -------- SIMPLE DATA TABLE --------
    if action == "get_simple_data_table":
        if use_json:
            return jsonify([])
        return Response("<data/>", content_type="application/xml")

    # -------- DEFAULT --------
    if use_json:
        return jsonify({"error": "action not handled", "action": action})
    return Response("<error>Action not handled</error>", content_type="application/xml")


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
