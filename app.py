from flask import Flask, redirect, request

app = Flask(__name__)

TARGET = "http://46.232.210.229:38510"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    if request.query_string:
        return redirect(f"{TARGET}/{path}?{request.query_string}", code=302)
    else:
        return redirect(f"{TARGET}/{path}", code=302)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
