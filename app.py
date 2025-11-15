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
    "John": "Sidford2025",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Default playlist
DEFAULT_M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
DEFAULT_EPG_URL = "http://m3u4u.com/xml/jwmzn1w282ukvxw4n721"

# Custom playlists
USER_M3U_URLS = {
    "John": "http://m3u4u.com/m3u/5g28nejz1zhv45q3yzpe",
    "main": "http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j"
}

# Matching EPG feeds
USER_EPG_URLS = {
    "John": DEFAULT_EPG_URL,   # John uses DEFAULT EPG
    "main": "http://m3u4u.com/xml/p87vnr8dzdu4w2q6n41j"
}

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


def get_epg_url_for_user(username):
    return USER_EPG_URLS.get(username, DEFAULT_EPG_URL)


def wants_json():
    """Only return JSON when output=json is explicitly requested."""
    return request.values.get("output", "").lower() == "json"


def list_to_xml(root_tag, item_tag, data_list):
    root = Element(root_tag)
    for item in data_list:
        item_elem = SubElement(root, item_tag)
        for key, val in item.items():
            child = SubElement(item_elem, key)
            child.text = "" if val is None else str(val)
    return tostring(root, encoding='unicode')


def fetch_m3u(url, username=""):
    now = time.time()

    # Use cached playlist if less than 24h old
    entry = _m3u_cache.get(url)
    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["parsed"]

    try:
        print(f"[M3U] Fetching: {url}")
        r = requests.get(url, headers=UA_HEADERS, timeout=20)
        r.raise_for_status()
        parsed = parse_m3u(r.text)

        _m3u_cache[url] = {
            "parsed": parsed,
            "ts": now
        }
        return parsed

    except Exception as e:
        print(f"[ERROR] Fetch failed: {e}")
        if entry:
            return entry["parsed"]
        return {"categories": [], "streams": [], "epg_url": None}


def fetch_m3u_for_user(username):
    return fetch_m3u(get_m3u_url_for_user(username), username)


def parse_m3u(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams = []
    categories = {}
    cat_id = 1
    stream_id = 1

    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')

    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))
            name = lines[i].split(",", 1)[1].strip()
            group = attrs.get("group-title", "Uncategorised")
            logo = attrs.get("tvg-logo", "")
            epg = attrs.get("tvg-id", "")

            i += 1
            url = lines[i] if i < len(lines) else ""

            if group not in categories:
                categories[group] = cat_id
                cat_id += 1

            streams.append({
                "stream_id": stream_id,
                "num": stream_id,
                "name": name,
                "stream_type": "live",
                "stream_icon": logo,
                "epg_channel_id": epg,
                "added": "1640000000",
                "category_id": str(categories[group]),
                "category_name": group,
                "direct_source": url,
                "container_extension": "m3u8"
            })

            stream_id += 1
        i += 1

    cats = [{"category_id": str(v), "category_name": k, "parent_id": 0} for k, v in categories.items()]
    return {"categories": cats, "streams": streams}


# ---------------- ROUTES ----------------

@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action", "")
    use_json = wants_json()

    if not valid_user(username, password):
        if use_json:
            return jsonify({"user_info": {"auth": 0}}), 403
        else:
            return Response("<response><user_info><auth>0</auth></user_info></response>",
                            status=403, content_type="application/xml")

    # Base login (action="")
    if action == "":
        info = {
            "user_info": {
                "auth": 1,
                "status": "Active",
                "username": username,
                "password": password,
                "allowed_output_formats": ["m3u8", "ts"]
            }
        }

        if use_json:
            return jsonify(info)
        else:
            xml = "<response><user_info>"
            for k, v in info["user_info"].items():
                if isinstance(v, list):
                    v = ",".join(v)
                xml += f"<{k}>{v}</{k}>"
            xml += "</user_info></response>"
            return Response(xml, content_type="application/xml")

    # Categories
    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        if use_json:
            return jsonify(cats)
        else:
            return Response(list_to_xml("categories", "category", cats),
                            content_type="application/xml")

    # Streams
    if action == "get_live_streams":
        data = fetch_m3u_for_user(username)
        cat_filter = request.values.get("category_id")
        streams = [s for s in data["streams"]
                   if not cat_filter or str(s["category_id"]) == str(cat_filter)]
        if use_json:
            return jsonify(streams)
        else:
            return Response(list_to_xml("streams", "channel", streams),
                            content_type="application/xml")

    # Unknown
    return Response("<error>Unknown action</error>",
                    status=400, content_type="application/xml")


# ------------- STREAMS (SAFE REDIRECT) -------------
@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
@app.route("/live/<username>/<password>/<int:stream_id>")
def live(username, password, stream_id, ext=None):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    data = fetch_m3u_for_user(username)

    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            target = s["direct_source"]
            print(f"[REDIRECT] {username} → {target}")
            return redirect(target, code=302)

    return Response("Stream not found", status=404)


# ---------------- EPG ----------------
@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    epg_url = get_epg_url_for_user(username)
    print(f"[EPG] {username} → {epg_url}")

    return redirect(epg_url)


# ---------------- DIRECT M3U ----------------
@app.route("/get.php")
def get_m3u():
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    return redirect(get_m3u_url_for_user(username))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
