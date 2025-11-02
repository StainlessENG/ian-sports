from flask import Flask, request, Response
import requests

app = Flask(__name__)

# Your new backend (seedbox) Flask app
BACKEND = "http://46.232.210.229:38510"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def proxy(path):
    # Build target URL (same path + query)
    target_url = f"{BACKEND}/{path}"
    if request.query_string:
        target_url += "?" + request.query_string.decode("utf-8")

    # Forward the request to the seedbox
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for key, value in request.headers if key.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=20
        )
    except requests.exceptions.RequestException as e:
        return Response(f"Proxy error: {str(e)}", status=502)

    # Filter headers
    excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
    headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]

    # Send it back to the IPTV client
    response = Response(resp.content, resp.status_code, headers)
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
