from flask import Flask, request, Response
import requests
import logging

app = Flask(__name__)

# your seedbox address + port
UPSTREAM = "http://46.232.210.229:38510"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "HEAD"])
@app.route("/<path:path>", methods=["GET", "POST", "HEAD"])
def proxy(path):
    # full target URL
    target = f"{UPSTREAM}/{path}"
    try:
        if request.method == "POST":
            resp = requests.post(target, data=request.form, headers=request.headers, timeout=10)
        else:
            resp = requests.get(target, params=request.args, headers=request.headers, timeout=10)
        excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded]
        logging.info(f"Proxy: {request.method} {target} → {resp.status_code}")
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        logging.error(f"Proxy error: {e}")
        return Response("Proxy error", status=502)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
