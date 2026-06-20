"""WSGI entry point for production servers (gunicorn, mod_wsgi, uWSGI).

    gunicorn --workers 3 --preload --bind 127.0.0.1:8000 wsgi:application

Apache mod_wsgi:  WSGIScriptAlias / /srv/chitralahar/wsgi.py

Use --preload (gunicorn) or a single mod_wsgi process so the one-time database
setup/migration runs once rather than racing across workers.
"""
from chitralahar import create_app

application = create_app()
