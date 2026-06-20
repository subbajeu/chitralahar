"""Entry point for the Chitralahar photography CMS.

Usage:
    ./.venv/bin/python run.py
Then open http://127.0.0.1:5050  (admin at /admin)
"""
import os

from chitralahar import create_app

app = create_app()

if __name__ == "__main__":
    # run.py is for LOCAL DEVELOPMENT ONLY (binds to loopback). In production use
    # wsgi:application behind gunicorn/Apache — never expose this server.
    # 5050 by default — macOS reserves 5000 for AirPlay Receiver.
    port = int(os.environ.get("PORT", "5050"))
    # Debug (Werkzeug reloader + interactive debugger) is OFF unless you opt in.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
