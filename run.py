"""Entry point: python run.py [--host 127.0.0.1] [--port 5000] [--seed]"""

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import create_app, db  # noqa: E402
from app.models import Book  # noqa: E402

SEED = [
    {"title": "The Pragmatic Programmer", "author": "Hunt & Thomas",
     "year": 1999, "genre": "Software", "rating": 4.7, "available": True},
    {"title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann",
     "year": 2017, "genre": "Software", "rating": 4.9, "available": True},
    {"title": "The Phoenix Project", "author": "Gene Kim",
     "year": 2013, "genre": "Fiction", "rating": 4.4, "available": False},
    {"title": "Clean Code", "author": "Robert C. Martin",
     "year": 2008, "genre": "Software", "rating": 4.3, "available": True},
    {"title": "The Art of Statistics", "author": "David Spiegelhalter",
     "year": 2019, "genre": "Statistics", "rating": 4.6, "available": True},
]


def seed(app) -> None:
    with app.app_context():
        if Book.query.first():
            print("Database already has rows; skipping seed.")
            return
        db.session.add_all(Book(**row) for row in SEED)
        db.session.commit()
        print(f"Seeded {len(SEED)} books.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Books REST API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--seed", action="store_true", help="insert sample rows then exit")
    args = parser.parse_args()

    app = create_app()

    if args.seed:
        seed(app)
        return 0

    print(f"Books API on http://{args.host}:{args.port}/api/v1/books")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
