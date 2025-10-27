from flask import Flask, request, Response, jsonify, redirect
import requests, re, time
from datetime import datetime

app = Flask(__name__)

# ===== USERS / PLAYLISTS =====
VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin",
}

USER_LINKS = {
    "dad":   {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "john":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "mark":  {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "james": {"m3u": "http://m3u4u.com/m3u/w16vy52exeax15kzn39p", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "ian":   {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "harry": {"m3u": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j", "epg": "http://m3u4u.com/epg/w16vy52exeax15kzn39p"},
    "main":  {"m3u": "http://m3u4u.com/m3u/476rnmqd4ds4rkd3nekg", "epg": "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"},
}

# ===== HELPERS =====
def check_auth():
    u, p = request.args.get("username",""), request.args.get("password","")
    if u in VALID_USERS and VALID_USERS[u] == p:
        return u
    return None

def parse_m3u(content):
    text = content.decode("utf-8", errors="ignore")
    channels, categories, current = [], {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            current = {
                "num": len(channels)+1, "name":"Unknown", "stream_icon":"",
                "stream_id": len(channels)+1, "category_id":"1",
                "category_name":"Uncategorized", "tvg_id":"", "stream_url":""
            }
            if "," in line: current["name"] = line.split(",",1)[1].strip()
            m = re.search(r'group-title="([^"]*)"', line)
            cat = m.group(1) if m else "Uncategorized"
            if cat not in categories:
                categories[cat] = str(len(categories)+1)
            current["category_name"], current["category_id"] = cat, categories[cat]
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m: current["tvg_id"] = m.group(1)
            m = re.search(r'tvg-logo="([^"]*)"', line)
            if m: current["stream_icon"] = m.group(1)
        elif not line.startswith("#") and current:
            current["stream_url"] = line
            channels.append(current)
            current = None
    for i,ch in enumerate(channels,1):
        ch["num"] = ch["stream_id"] = i
    return channels, categories

# ===== ROUTES =====
@app.route("/")
def index():
    out=["=== IPTV Access Links ===",""]
    for u in USER_LINKS:
        out.append(f"User: {u}")
        out.append(f"M3U: /get.php?username={u}&password={VALID_USERS[u]}")
        out.append(f"EPG: /xmltv.php?username={u}&password={VALID_USERS[u]}\n")
    return Response("\n".join(out),mimetype="text/plain")

@app.route("/get.php")
def get_php():
    u = check_auth()
    if not u:
        return Response("Invalid credentials", 403)
    return redirect(USER_LINKS[u]["m3u"], 302)

@app.route("/xmltv.php")
def xmltv():
    u = check_auth()
    if not u:
        return Response("Invalid credentials", 403)
    return redirect(USER_LINKS[u]["epg"], 302)

@app.route("/player_api.php")
def player_api():
    u = check_auth()
    if not u:
        return jsonify({"user_info": {"auth": 0, "status": "Disabled"}})
    act = request.args.get("action", "")

    # --- Login / basic info ---
    if not act:
        return jsonify({
            "user_info": {
                "auth": 1,
                "password": VALID_USERS[u],
                "status": "Active",
                "username": u
            },
            "server_info": {
                "server_protocol": "https",
                "timestamp_now": str(int(time.time())),
                "url": request.host
            }
        })

    # --- Get live categories ---
    if act == "get_live_categories":
        try:
            r = requests.get(USER_LINKS[u]["m3u"], timeout=10)
            _, cats = parse_m3u(r.content)
            return jsonify([{"category_id": cid, "category_name": cn, "parent_id": 0} for cn, cid in cats.items()])
        except Exception:
            return jsonify([])

    # --- Get live streams ---
    if act == "get_live_streams":
        try:
            r = requests.get(USER_LINKS[u]["m3u"], timeout=10)
            chans, cats = parse_m3u(r.content)
            return jsonify([
                {
                    "num": c["num"],
                    "name": c["name"],
                    "stream_type": "live",
                    "stream_id": c["stream_id"],
                    "stream_icon": c["stream_icon"],
                    "category_id": c["category_id"],
                    "direct_source": c["stream_url"],
                    "epg_channel_id": c["tvg_id"]
                } for c in chans
            ])
        except Exception:
            return jsonify([])

    return jsonify([])

# ---- Redirect to real stream (no proxy) ----
@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Invalid login", 403)
    try:
        r = requests.get(USER_LINKS[username]["m3u"], timeout=10)
        chans, _ = parse_m3u(r.content)
        for c in chans:
            if c["stream_id"] == stream_id:
                return redirect(c["stream_url"], 302)
    except Exception as e:
        print(f"Redirect error: {e}")
    return Response("Stream not found", 404)

# ---- Fallback for /user/pass/id ----
@app.route("/<username>/<password>/<int:stream_id>")
def fallback_redirect(username, password, stream_id):
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("Invalid login", 403)
    try:
        r = requests.get(USER_LINKS[username]["m3u"], timeout=10)
        chans, _ = parse_m3u(r.content)
        for c in chans:
            if c["stream_id"] == stream_id:
                return redirect(c["stream_url"], 302)
    except Exception as e:
        print(f"Fallback error: {e}")
    return Response("Stream not found", 404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
