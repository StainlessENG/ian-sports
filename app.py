from flask import Flask, request, Response, stream_with_context
import requests

app = Flask(__name__)

# Your seedbox backend
BACKEND = "http://46.232.210.229:38510"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def proxy(path):
    # Build target URL
    target_url = f"{BACKEND}/{path}"
    if request.query_string:
        target_url += "?" + request.query_string.decode("utf-8")
    
    print(f"[PROXY] {request.method} {path}")
    
    # Forward headers (exclude host)
    headers = {key: value for key, value in request.headers if key.lower() != 'host'}
    
    try:
        # Make request with streaming enabled
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=True,
            stream=True,
            timeout=30
        )
        
        # Stream response back
        def generate():
            try:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                print(f"[PROXY] Stream error: {e}")
        
        # Build response headers
        excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        response_headers = [(name, value) for name, value in resp.raw.headers.items() 
                           if name.lower() not in excluded]
        
        return Response(
            stream_with_context(generate()),
            status=resp.status_code,
            headers=response_headers,
            direct_passthrough=True
        )
            
    except requests.exceptions.RequestException as e:
        print(f"[PROXY] Error: {e}")
        return Response(f"Proxy error: {str(e)}", status=502)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
