import os, time, re, requests
from flask import Flask, request, redirect, jsonify, Response
from xml.etree.ElementTree import Element, SubElement, tostring

app = Flask(__name__)

# ------------- CONFIG -----------------
USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

M3U_URL = "https://raw.githubusercontent.com/StainlessENG/ian-sports/refs/heads/main/Main%20Playlist.m3u"
CACHE_TTL = 600  # seconds
# --------------------------------------

_m3u_cache = {"ts": 0, "text": "", "parsed": None}


# --------- HELPERS ----------
def valid_user(username, password):
    return username in USERS and USERS[username] == password


def fetch_m3u():
    """Fetch and cache the M3U file."""
    now = time.time()
    if _m3u_cache["parsed"] is not None and (now - _m3u_cache["ts"] < CACHE_TTL):
        return _m3u_cache["parsed"]

    resp = requests.get(M3U_URL, timeout=15)
    resp.raise_for_status()
    text = resp.text
    parsed = parse_m3u(text)
    _m3u_cache.update({"ts": now, "text": text, "parsed": parsed})
    return parsed


def parse_m3u(text):
    """Parse M3U into categories and streams."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams, cat_map, next_id, stream_id = [], {}, 1, 1
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
                cat_map[group] = next_id
                next_id += 1

            streams.append({
                "stream_id": stream_id,
                "name": name,
                "url": url,
                "logo": logo,
                "epg_id": epg_id,
                "category_id": cat_map[group],
                "category_name": group
            })
            stream_id += 1
            i = j
        else:
            i += 1

    categories = [{"category_id": cid, "category_name": name, "parent_id": 0}
                  for name, cid in sorted(cat_map.items(), key=lambda x: x[1])]
    return {"categories": categories, "streams": streams}


def make_xml(data):
    """Convert dict/list response to XML (basic Xtream style)."""
    root = Element("response")

    def add_sub(parent, tag, value):
        el = SubElement(parent, tag)
        el.text = str(value)
        return el

    # For category lists
    if isinstance(data, list) and data and "category_id" in data[0]:
        for cat in data:
            cat_el = SubElement(root, "category")
            for k, v in cat.items():
                add_sub(cat_el, k, v)
    # For stream lists
    elif isinstance(data, list) and data and "stream_id" in data[0]:
        for ch in data:
            ch_el = SubElement(root, "channel")
            for k, v in ch.items():
                add_sub(ch_el, k, v)
    # For info dict
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                parent = SubElement(root, k)
                for kk, vv in v.items():
                    add_sub(parent, kk, vv)
            else:
                add_sub(root, k, v)
    else:
        add_sub(root, "message", "Empty")

    xml_bytes = tostring(root, encoding="utf-8")
    return Response(xml_bytes, content_type="application/xml; charset=utf-8")
# -----------------------------


@app.route("/")
def index():
    return "✅ Xtream Bridge running OK (JSON + XML Dual Mode)"


@app.route("/get.php")
def get_m3u():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(M3U_URL)


@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action", "")
    wants_xml = "xml" in (request.headers.get("Accept", "") + request.headers.get("Content-Type", "")).lower()

    if not valid_user(username, password):
        data = {"user_info": {"auth": 0, "status": "Unauthorized"}, "message": "Unauthorized", "auth": 0}
        return make_xml(data) if wants_xml else jsonify(data)

    # --- ACTION HANDLING ---
    if action == "get_live_categories":
        cats = fetch_m3u()["categories"]
        return make_xml(cats) if wants_xml else jsonify(cats)

    if action == "get_live_streams":
        data = fetch_m3u()
        cat_filter = request.args.get("category_id")
        out = []
        for s in data["streams"]:
            if cat_filter and str(s["category_id"]) != str(cat_filter):
                continue
            out.append({
                "num": str(s["stream_id"]),
                "name": s["name"],
                "stream_type": "live",
                "stream_id": s["stream_id"],
                "stream_icon": s["logo"],
                "epg_channel_id": s["epg_id"],
                "category_id": str(s["category_id"]),
                "direct_source": s["url"]
            })
        return make_xml(out) if wants_xml else jsonify(out)

    # Empty VOD/Series stubs
    if action in ["get_vod_categories", "get_series_categories", "get_vod_streams", "get_series"]:
        empty = []
        return make_xml(empty) if wants_xml else jsonify(empty)

    # Default (login info)
    data = {
        "user_info": {
            "auth": 1,
            "username": username,
            "status": "Active",
            "exp_date": "UNLIMITED",
            "is_trial": "0",
            "active_cons": "1"
        },
        "server_info": {
            "url": request.host,
            "port": 443,
            "https_port": 443,
            "server_protocol": "https"
        },
        "message": "Active",
        "auth": 1
    }
    return make_xml(data) if wants_xml else jsonify(data)


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    data = fetch_m3u()
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return redirect(s["url"])
    return Response("Stream not found", status=404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
