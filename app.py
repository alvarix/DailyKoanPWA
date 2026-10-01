# pyright: reportMissingImports=false
"""
Flask application for Daily Koan PWA.

Serves the PWA frontend, provides API endpoints for koans and push subscriptions.
"""

import hashlib
import json
import os
import sqlite3
import warnings
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_from_directory

DB_PATH = os.path.join(os.path.dirname(__file__), 'subscriptions.db')
KOANS_PATH = os.path.join(os.path.dirname(__file__), 'koans.json')

def load_koans():
    try:
        with open(KOANS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load koans: {e}") from e

# Load VAPID public key if available
VAPID_PUBLIC_KEY = None
vapid_public_path = os.path.join(os.path.dirname(__file__), 'vapid_public.pem')
if os.path.exists(vapid_public_path):
    try:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import b64urlencode
        with open(vapid_public_path, 'rb') as f:
            key = serialization.load_pem_public_key(f.read())
        VAPID_PUBLIC_KEY = b64urlencode(key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        ))
    except Exception as e:
        warnings.warn(f"Failed to load VAPID public key: {e}", stacklevel=2)
        VAPID_PUBLIC_KEY = None

app = Flask(__name__)

# ----------- Helpers -----------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_todays_koan():
    """Return a deterministic koan based on today's date."""
    koans = load_koans()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    idx = int(hashlib.sha256(today.encode()).hexdigest(), 16) % len(koans)
    return koans[idx], idx


# ----------- Routes -----------

@app.route('/')
def index():
    """Serve the main PWA page."""
    koans = load_koans()
    koan, idx = get_todays_koan()
    return render_template('index.html', koan=koan, koan_index=idx, total_koans=len(koans), vapid_public_key=VAPID_PUBLIC_KEY)


@app.route('/koan/<int:index>')
def koan_by_index(index):
    """Serve a specific koan by index."""
    koans = load_koans()
    if 0 <= index < len(koans):
        koan = koans[index]
        return render_template('index.html', koan=koan, koan_index=index, total_koans=len(koans), vapid_public_key=VAPID_PUBLIC_KEY)
    return jsonify({'error': 'Koan not found'}), 404


@app.route('/api/today')
def api_today():
    """API: return today's koan as JSON."""
    koan, idx = get_todays_koan()
    return jsonify({'koan': koan, 'index': idx, 'total': len(load_koans())})


@app.route('/api/koan/<int:index>')
def api_koan(index):
    """API: return a specific koan as JSON."""
    koans = load_koans()
    if 0 <= index < len(koans):
        return jsonify({'koan': koans[index], 'index': index, 'total': len(koans)})
    return jsonify({'error': 'Koan not found'}), 404


@app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    """Store a push subscription from the browser."""
    data = request.get_json()
    if not data or 'endpoint' not in data or 'keys' not in data:
        return jsonify({'error': 'Invalid subscription data'}), 400

    endpoint = data['endpoint']
    p256dh = data['keys'].get('p256dh')
    auth = data['keys'].get('auth')

    if not p256dh or not auth:
        return jsonify({'error': 'Missing keys'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO subscriptions (endpoint, p256dh, auth) VALUES (?, ?, ?)',
        (endpoint, p256dh, auth)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True}), 201


@app.route('/api/unsubscribe', methods=['POST'])
def api_unsubscribe():
    """Remove a push subscription."""
    data = request.get_json()
    endpoint = data.get('endpoint') if data else None
    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE endpoint = ?', (endpoint,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@app.route('/manifest.json')
def manifest():
    """Serve the PWA manifest."""
    return send_from_directory('static', 'manifest.json')


@app.route('/sw.js')
def service_worker():
    """Serve the service worker."""
    return send_from_directory('static', 'sw.js')


@app.route('/api/subscriptions/count')
def subscription_count():
    """Admin/debug: count active subscriptions."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM subscriptions')
    count = cursor.fetchone()[0]
    conn.close()
    return jsonify({'count': count})


# --- Error handlers ---

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


if __name__ == '__main__':
    app.run(host=os.environ.get('FLASK_HOST', '127.0.0.1'), port=int(os.environ.get('PORT', 5000)), debug=os.environ.get('FLASK_DEBUG', '1') == '1')
