from flask import Flask, request, Response
import requests

app = Flask(__name__)

# --- Config ---
DEFAULT_M3U = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"
SPECIAL_USERS = {
    "ian": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j",
    "harry": "http://m3u4u.com/m3u/p87vnr8dzdu4w2r1n41j"
}
VALID_USERS = {
    "dad": "devon",
    "john": "pass123",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025"
}
# --------------

@app.route('/')
def home():
    return "<h3>Xtream Bridge Base: Running ✅</h3>"

@app.route('/get.php')
def get_php():
    username = request.args.get('username', '')
    password = request.args.get('password', '')

    # Case-insensitive username matching
    username_key = username.lower()
    valid = any(
        username_key == u.lower() and password == p
        for u, p in VALID_USERS.items()
    )

    if not valid:
        return Response("Invalid credentials", status=403)

    # Match to correct M3U source
    m3u_url = SPECIAL_USERS.get(username_key, DEFAULT_M3U)

    try:
        resp = requests.get(m3u_url, timeout=10)
        if resp.status_code != 200:
            return Response(f"Error fetching M3U: {resp.status_code}", status=500)
        return Response(resp.content, mimetype='application/x-mpegURL')
    except Exception as e:
        return Response(f"Exception: {str(e)}", status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
