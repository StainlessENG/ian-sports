from flask import Flask, request, redirect, Response

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

# Direct GitHub M3U link
M3U_URL = "https://raw.githubusercontent.com/StainlessENG/ian-sports/refs/heads/main/Main%20Playlist.m3u"

@app.route("/get.php")
def get_m3u():
    username = request.args.get("username")
    password = request.args.get("password")
    m3u_type = request.args.get("type", "m3u_plus")

    # Validate user
    if username not in USERS or USERS[username] != password:
        return Response("Invalid credentials", status=403)

    # Only return playlist for supported types
    if m3u_type in ("m3u", "m3u_plus"):
        return redirect(M3U_URL)
    else:
        return Response("Unsupported type", status=400)

@app.route("/")
def index():
    return "✅ Xtream Bridge running OK - M3U Redirect Active"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
