from flask import Flask, request, Response, jsonify, redirect
import requests
from datetime import datetime
from collections import defaultdict
import time
import re

app = Flask(__name__)

# --- CONFIG ---
# Default source (for everyone else)
M3U_URL = "http://m3u4u.com/m3u/w16vy52exeax15kzn39p"
EPG_URL = "http://m3u4u.com/epg/w16vy52exeax15kzn39p"

# Special source for Ian and Harry
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

MAX_CONNECTIONS_PER_USER = 2
ADMIN_PASSWORD = "admin123"
# ----------------

# Global tracking
active_sessions = {}
connection_history = []
user_stats = defaultdict(lambda: {"total_fetches": 0, "last_fetch": None})
cached_m3u = None
cached_channels = []
cached_categories = {}
cache_time = 0

def parse_m3u(content):
    channels = []
    categories = {}
    try:
        text = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else content
        lines = text.split('\n')
        current_channel = {}
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                current_channel = {
                    'num': len(channels) + 1,
                    'name': 'Unknown Channel',
                    'stream_icon': '',
                    'stream_id': len(channels) + 1,
                    'category_id': '1',
                    'category_name': 'Uncategorized',
                    'tvg_id': '',
                    'stream_url': ''
                }
                if ',' in line:
                    name_part = line.split(',', 1)[1].strip()
                    if name_part:
                        current_channel['name'] = name_part
                group_match = re.search(r'group-title="([^"]*)"', line)
                if group_match:
                    category_name = group_match.group(1)
                    current_channel['category_name'] = category_name
                    if category_name not in categories:
                        categories[category_name] = str(len(categories) + 1)
                    current_channel['category_id'] = categories[category_name]
                tvg_match = re.search(r'tvg-id="([^"]*)"', line)
                if tvg_match:
                    current_channel['tvg_id'] = tvg_match.group(1)
                logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                if logo_match:
                    current_channel['stream_icon'] = logo_match.group(1)
            elif line and not line.startswith('#'):
                if current_channel:
                    current_channel['stream_url'] = line
                    channels.append(current_channel.copy())
                    current_channel = {}
    except Exception as e:
        print(f"Error parsing M3U: {e}")
        channels = [{
            'num': 1, 'name': 'Test Channel (Parser Error)', 'stream_icon': '',
            'stream_id': 1, 'category_id': '1', 'category_name': 'Test',
            'tvg_id': 'test', 'stream_url': 'http://test.com/stream.m3u8'
        }]
        categories = {'Test': '1'}
    return channels, categories

def get_cached_channels():
    global cached_channels, cached_categories, cache_time, cached_m3u

    username = request.args.get('username', '').lower()
    user_m3u_url = SPECIAL_USERS.get(username, M3U_URL)

    if time.time() - cache_time < 300 and cached_channels and cached_categories:
        return cached_channels, cached_categories, cached_m3u

    try:
        resp = requests.get(user_m3u_url, timeout=10)
        if resp.status_code == 200:
            cached_m3u = resp.content
            result = parse_m3u(resp.content)
            if isinstance(result, tuple):
                cached_channels, cached_categories = result
            else:
                cached_channels = result
                cached_categories = {'Uncategorized': '1'}
            cache_time = time.time()
            print(f"Loaded {len(cached_channels)} channels in {len(cached_categories)} categories from {user_m3u_url}")
        else:
            print(f"Failed to fetch M3U: Status {resp.status_code}")
    except Exception as e:
        print(f"Error fetching M3U: {e}")
        import traceback; traceback.print_exc()

    return cached_channels, cached_categories, cached_m3u

# ... (the rest of your routes remain exactly the same as in THIS.py)
