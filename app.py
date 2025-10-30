from flask import Flask, request, Response
import requests

app = Flask(__name__)

# 👇 Your seedbox backend (Flask) address and port
TARGET = "http://46.232.210.229:38510"

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy(path):
    from urllib.parse import urlencode

    # Preserve the full query string (?username=main&password=admin)
    qs = request.query_string.decode('utf-8')
    url = f"{TARGET}/{path}"
    if qs:
        url = f"{url}?{qs}"

    try:
        # Forward the request to your seedbox backend
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for key, value in request.headers if key.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30
        )

        # Remove headers that can break proxying
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        # Return the seedbox response to the client
        response = Response(resp.content, resp.status_code, headers)
        return response

    except requests.exceptions.RequestException as e:
        # If the backend can’t be reached, return a 502 error
        return f"Upstream error: {e}", 502

if __name__ == "__main__":
    # Render listens on port 10000 by default
    app.run(host="0.0.0.0", port=10000)
