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


@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action", "")

    if not valid_user(username, password):
        xml_root = Element("xml")
        user_info = SubElement(xml_root, "user_info")
        SubElement(user_info, "auth").text = "0"
        SubElement(user_info, "status").text = "Unauthorized"
        xml_bytes = tostring(xml_root, encoding="utf-8")
        return Response(xml_bytes, content_type="application/xml; charset=utf-8")

    # -------- LOGIN INFO (no action) --------
    if action == "":
        xml_root = Element("xml")
        user_info = SubElement(xml_root, "user_info")
        SubElement(user_info, "auth").text = "1"
        SubElement(user_info, "username").text = username
        SubElement(user_info, "password").text = password
        SubElement(user_info, "status").text = "Active"
        SubElement(user_info, "message").text = "Active"
        SubElement(user_info, "exp_date").text = "UNLIMITED"
        SubElement(user_info, "is_trial").text = "0"
        SubElement(user_info, "active_cons").text = "1"

        server_info = SubElement(xml_root, "server_info")
        SubElement(server_info, "url").text = request.host
        SubElement(server_info, "port").text = "80"
        SubElement(server_info, "https_port").text = "443"
        SubElement(server_info, "server_protocol").text = "http"
        SubElement(server_info, "timezone").text = "Europe/London"
        SubElement(server_info, "timestamp_now").text = str(int(time.time()))
        SubElement(server_info, "time_now").text = time.strftime("%Y-%m-%d %H:%M:%S")
        SubElement(server_info, "x_tvg_url").text = EPG_URL

        xml_bytes = tostring(xml_root, encoding="utf-8")
        return Response(xml_bytes, content_type="application/xml; charset=utf-8")

    # -------- LIVE CATEGORIES --------
    if action == "get_live_categories":
        cats = fetch_m3u()["categories"]
        xml_root = Element("xml")
        for c in cats:
            el = SubElement(xml_root, "category")
            for k, v in c.items():
                SubElement(el, k).text = str(v)
        xml_bytes = tostring(xml_root, encoding="utf-8")
        return Response(xml_bytes, content_type="application/xml; charset=utf-8")

    # -------- LIVE STREAMS --------
    if action == "get_live_streams":
        data = fetch_m3u()
        cat_filter = request.args.get("category_id")
        xml_root = Element("xml")
        for s in data["streams"]:
            if cat_filter and str(s["category_id"]) != str(cat_filter):
                continue
            ch = SubElement(xml_root, "channel")
            SubElement(ch, "num").text = str(s["stream_id"])
            SubElement(ch, "name").text = s["name"]
            SubElement(ch, "stream_type").text = "live"
            SubElement(ch, "stream_id").text = str(s["stream_id"])
            SubElement(ch, "stream_icon").text = s["logo"]
            SubElement(ch, "epg_channel_id").text = s["epg_id"]
            SubElement(ch, "category_id").text = str(s["category_id"])
            SubElement(ch, "direct_source").text = s["url"]
        xml_bytes = tostring(xml_root, encoding="utf-8")
        return Response(xml_bytes, content_type="application/xml; charset=utf-8")

    # -------- EMPTY STUBS (VOD/SERIES) --------
    empty_xml = Element("xml")
    xml_bytes = tostring(empty_xml, encoding="utf-8")
    return Response(xml_bytes, content_type="application/xml; charset=utf-8")


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
