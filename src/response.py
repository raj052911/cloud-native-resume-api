"""
response.py
-----------
Reusable HTTP response factory functions for the Serverless Resume API.

All Lambda handlers return a dict that API Gateway converts into an
HTTP response. This module centralises that formatting so handlers
stay clean and consistent.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Standard CORS + content-type headers for every response.
_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def success(data: dict | list, message: str = "Success") -> dict:
    """
    Return HTTP 200 with a JSON body.

    Args:
        data:    The payload to include under the ``data`` key.
        message: Optional human-readable status message.

    Returns:
        API Gateway-compatible response dict.
    """
    body = {
        "status": "success",
        "message": message,
        "data": data,
    }
    return _build_response(200, body)


def not_found(resource: str = "Resource") -> dict:
    """
    Return HTTP 404 when a requested resume section is absent from DynamoDB.

    Args:
        resource: Name of the missing resource for the error message.
    """
    body = {
        "status": "error",
        "message": f"{resource} not found.",
        "data": None,
    }
    return _build_response(404, body)


def bad_request(detail: str = "Invalid request.") -> dict:
    """
    Return HTTP 400 for malformed or unrecognised requests.

    Args:
        detail: Human-readable explanation of the problem.
    """
    body = {
        "status": "error",
        "message": detail,
        "data": None,
    }
    return _build_response(400, body)


def method_not_allowed(method: str = "") -> dict:
    """
    Return HTTP 405 when the HTTP method is not GET.

    Args:
        method: The unsupported HTTP method that was attempted.
    """
    detail = f"HTTP method '{method}' is not allowed. Use GET." if method else "Method not allowed."
    body = {
        "status": "error",
        "message": detail,
        "data": None,
    }
    return _build_response(405, body)


def server_error(detail: str = "An internal server error occurred.") -> dict:
    """
    Return HTTP 500 for unexpected exceptions.

    Never exposes internal exception details to the caller.

    Args:
        detail: A safe, generic message (do NOT pass raw exception text).
    """
    body = {
        "status": "error",
        "message": detail,
        "data": None,
    }
    return _build_response(500, body)


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build_response(status_code: int, body: dict) -> dict:
    """Serialise *body* to JSON and wrap it in an API Gateway response dict."""
    return {
        "statusCode": status_code,
        "headers": _BASE_HEADERS,
        "body": json.dumps(body, default=str),
    }
