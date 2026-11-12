"""HTTP caching with ETags (conditional requests).

The server sends an ETag, a fingerprint of the response body. The client
sends it back in If-None-Match; if the data hasn't changed, the server
answers 304 Not Modified with an empty body, and the client reuses its copy.
"""

import hashlib
import json
from typing import Any

from fastapi import Request, Response, status
from fastapi.encoders import jsonable_encoder


def json_with_etag(request: Request, data: Any) -> Response:
    body = json.dumps(jsonable_encoder(data), separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(body, media_type="application/json", headers=headers)
