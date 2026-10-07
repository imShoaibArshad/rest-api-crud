"""Error handling.

Every failure leaves through here, so the JSON shape stays consistent:
    {"error": {"code": "...", "message": "...", "fields": {...}}}
"""

from flask import Blueprint, jsonify
from werkzeug.exceptions import HTTPException

bp = Blueprint("errors", __name__)


def error_response(status: int, code: str, message: str, fields: dict | None = None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return jsonify(body), status


@bp.app_errorhandler(HTTPException)
def handle_http(exc):
    """Normalise Flask's own HTML error pages into JSON."""
    return error_response(exc.code, exc.name.lower().replace(" ", "_"), exc.description)


@bp.app_errorhandler(405)
def handle_method_not_allowed(exc):
    return error_response(405, "method_not_allowed", "That method isn't supported here.")


@bp.app_errorhandler(404)
def handle_not_found(exc):
    return error_response(404, "not_found", "Resource not found.")


@bp.app_errorhandler(Exception)
def handle_unexpected(exc):
    """Never leak a stack trace to the client."""
    from . import db
    db.session.rollback()
    app = exc.__dict__.get("app")
    if app is None:
        from flask import current_app
        current_app.logger.exception("unhandled error")
    return error_response(500, "internal_error", "Unexpected server error.")
