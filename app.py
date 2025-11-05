from flask import Flask, request, redirect, jsonify, Response

app = Flask(__name__)

# Users and passwords
USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# Direct M3U link
M3U_URL = "https://raw.githubusercontent.com/StainlessENG/ian-sports/refs/heads/main/Main%20Playlist.m3u"

def valid_user(username, password):
    return username in USERS and USERS[username] == password

@app.route("/")
def index():
    return "✅ Xtream Bridge running OK"

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
        return jsonify({"user_info": {"auth": 0, "status": "Unauthorized"}})

    # Simple fake Xtream response just to keep players happy
    if action in ["get_live_categories", "get_vod_categories", "get_series_categories"]:
        return jsonify([])

    elif action in ["get_live_streams", "get_vod_streams", "get_series"]:
        return jsonify([])

    else:
        # default user info response
        return jsonify({
            "user_info": {
                "auth": 1,
                "username": username,
                "status": "Active",
                "exp_date": "UNLIMITED",
                "is_trial": "0",
                "active_cons": "1"
            },
            "server_info": {
                "url": "your-app-name.onrender.com",
                "port": 443,
                "https_port": 443,
                "server_protocol": "https"
            }
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
