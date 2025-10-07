from flask import Flask, request, Response
import requests

app = Flask(__name__)

# --- CONFIG ---
M3U_URL = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"  # your m3u4u link
VALID_USERS = {"sid": "devon", "john": "pass123"}  # username/password for login
# ----------------

@app.route('/get.php')
def get_php():
    username = request.args.get('username', '')
    password = request.args.get('password', '')
    
    if username not in VALID_USERS or VALID_USERS[username] != password:
        return Response("User not found or bad password", status=403)
    
    resp = requests.get(M3U_URL)
    if resp.status_code != 200:
        return Response("Could not fetch M3U", status=500)
    
    return Response(resp.content, mimetype='application/x-mpegURL')

@app.route('/')
def home():
    return "Xtream bridge active! Use /get.php?username=sid&password=devon&type=m3u_plus"
