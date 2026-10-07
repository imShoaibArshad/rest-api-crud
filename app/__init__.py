"""Application factory and extension wiring.

Separated from the business logic so tests can spin up an isolated app with
an in-memory database instead of touching the dev one.
"""

import os
from pathlib import Path

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

db = SQLAlchemy()


class Base(DeclarativeBase):
    """Single declarative base — SQLAlchemy 2.x style."""


def create_app(config: dict | None = None) -> Flask:
    """Build an app. Tests pass `config` to swap in a scratch database."""
    app = Flask(__name__)

    default_db = Path(__file__).resolve().parent.parent / "books.db"
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("DATABASE_URL", f"sqlite:///{default_db}"),
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("JSON_SORT_KEYS", False)
    if config:
        app.config.update(config)

    db.init_app(app)

    # Import here to avoid a circular import at module load time.
    from .errors import bp as errors_bp
    from .routes import api_bp

    app.register_blueprint(errors_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    with app.app_context():
        db.create_all()

    return app
