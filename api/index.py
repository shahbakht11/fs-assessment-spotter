"""Vercel serverless entry point: exposes the Django WSGI app for every /api/* request.

vercel.json rewrites /api/<path> to this function as /api/index.py?__path=<path>. Vercel
may hand the function either the original or the rewritten URL, so the real path is
restored from `__path` before Django routes the request.
"""

import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application as django_app  # noqa: E402

PATH_PARAM = "__path"


def app(environ, start_response):
    query = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    original = [v for k, v in query if k == PATH_PARAM]
    if original:
        environ["PATH_INFO"] = "/api/" + original[0].lstrip("/")
        environ["QUERY_STRING"] = urlencode([(k, v) for k, v in query if k != PATH_PARAM])
    return django_app(environ, start_response)
