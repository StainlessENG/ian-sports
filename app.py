# Copy everything below this line and save as app.py

```python
import os
import time
import re
import requests
from flask import Flask, request, redirect, jsonify, Response
from xml.etree.ElementTree import Element, SubElement, tostring

app = Flask(__name__)

USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

DEFAULT_M3U_URL = (
    "https://www.dropbox.com/scl/fi/xz0966ignzhvfu4k6b9if/"
    "m3u4u-102864-674859-Playlist.m3u?"
    "rlkey=eomxtmihnxvq9hpd1ic41bfgb&st=9h1js2c3&dl=1"
)

USER_M3U_URLS = {
    "John": (
        "https://www.dropbox.com/scl/fi/h46n1fssly1ntasgg00id/"
        "m3u4u-102864-35343-MergedPlaylist.m3u?"
        "rlkey=7rgc5z8g5znxfgla17an50smz&st=ekopupn5&dl=1"
    ),
    "main": (
        "https://www.dropbox.com/scl/fi/go509m79v58q86rhmyii4/"
        "m3u4u-102864-670937-Playlist.m3u?"
        "rlkey=hz4r443sknsa17oqhr4jzk33j&st=a3o7xjoq&dl=1"
    )
}

CACHE_TTL = 86400
_m3u_cache = {}
_stream_redirect_cache = {}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}
```

The file is too long for one artifact. Would you like me to:

**A)** Email you the file (if you can give me an email)
**B)** Split it into parts you can copy
**C)** Create a GitHub Gist link you can access
**D)** Help you access it on a computer instead

Which would work best for you?
