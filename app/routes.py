"""CRUD endpoints for /api/v1/books.

Design notes:
  * List supports pagination, filtering, free-text search and sorting —
    without these, a "list" endpoint on a real table is a liability.
  * POST  -> 201 + Location header
    PUT   -> full replace, 200
    PATCH -> partial update, 200
    DELETE -> 204 no content
  * Client-supplied IDs are never accepted; the server assigns them.
"""

from flask import Blueprint, jsonify, request, url_for
from sqlalchemy import asc, desc, or_

from . import db
from .errors import error_response
from .models import Book
from .validation import validate

api_bp = Blueprint("api", __name__)

SORTABLE = {
    "id": Book.id,
    "title": Book.title,
    "author": Book.author,
    "year": Book.year,
    "genre": Book.genre,
    "rating": Book.rating,
    "created_at": Book.created_at,
    "updated_at": Book.updated_at,
}
MAX_PER_PAGE = 100


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "books-api", "version": "1.0.0"})


# ------------------------------------------------------------------ helpers --


def _get_or_404(book_id: int) -> Book | None:
    return db.session.get(Book, book_id)


def _parse_bool(raw: str | None, field: str, errors: dict) -> bool | None:
    if raw is None:
        return None
    lowered = raw.strip().lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    errors[field] = f"expected true or false, got {raw!r}"
    return None


# --------------------------------------------------------------------- list --


@api_bp.get("/books")
def list_books():
    """GET /books?page=1&per_page=20&q=&genre=&author=&year=&available=
              &sort=title&order=asc"""
    errors: dict[str, str] = {}

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=20, type=int)
    if page < 1:
        errors["page"] = "must be >= 1"
    if not 1 <= per_page <= MAX_PER_PAGE:
        errors["per_page"] = f"must be between 1 and {MAX_PER_PAGE}"

    available = _parse_bool(request.args.get("available"), "available", errors)
    year = request.args.get("year", type=int)

    sort_key = request.args.get("sort", "id")
    if sort_key not in SORTABLE:
        errors["sort"] = f"must be one of: {', '.join(sorted(SORTABLE))}"
    order = request.args.get("order", "asc").lower()
    if order not in ("asc", "desc"):
        errors["order"] = "must be 'asc' or 'desc'"

    if errors:
        return error_response(400, "validation_error", "Invalid query parameters.", errors)

    query = Book.query

    # Free-text search across the fields a user would actually type.
    if q := request.args.get("q", "").strip():
        term = f"%{q}%"
        query = query.filter(or_(
            Book.title.ilike(term),
            Book.author.ilike(term),
            Book.genre.ilike(term),
        ))

    if genre := request.args.get("genre", "").strip():
        query = query.filter(Book.genre.ilike(genre))
    if author := request.args.get("author", "").strip():
        query = query.filter(Book.author.ilike(f"%{author}%"))
    if year is not None:
        query = query.filter(Book.year == year)
    if available is not None:
        query = query.filter(Book.available.is_(available))

    column = SORTABLE[sort_key]
    query = query.order_by(desc(column) if order == "desc" else asc(column))

    # Secondary sort on id keeps pagination stable when the sort key ties.
    pagination = query.order_by(column, Book.id).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Carry the current filters/search/sort into the next/prev links, but drop
    # page & per_page — they are passed explicitly and url_for() rejects
    # duplicates.
    carried = {k: v for k, v in request.args.to_dict(flat=True).items()
               if k not in ("page", "per_page")}

    def page_link(target: int) -> str:
        return url_for("api.list_books", page=target, per_page=per_page, **carried)

    return jsonify({
        "data": [b.to_dict() for b in pagination.items],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
            "next": page_link(pagination.page + 1) if pagination.has_next else None,
            "prev": page_link(pagination.page - 1) if pagination.has_prev else None,
        },
    })


# --------------------------------------------------------------------- get --


@api_bp.get("/books/<int:book_id>")
def get_book(book_id: int):
    book = _get_or_404(book_id)
    if book is None:
        return error_response(404, "not_found", f"Book {book_id} does not exist.")
    return jsonify({"data": book.to_dict()})


# ------------------------------------------------------------------- create --


@api_bp.post("/books")
def create_book():
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "invalid_json",
                              "Request body must be valid JSON with Content-Type: application/json.")

    cleaned, errors = validate(payload, partial=False)
    if errors:
        return error_response(400, "validation_error", "Book could not be created.", errors)

    book = Book(**cleaned)
    db.session.add(book)
    db.session.commit()

    return (
        jsonify({"data": book.to_dict()}),
        201,
        {"Location": url_for("api.get_book", book_id=book.id)},
    )


# --------------------------------------------------------------------- put --


@api_bp.put("/books/<int:book_id>")
def replace_book(book_id: int):
    """PUT = full replacement. Every required field must be present."""
    book = _get_or_404(book_id)
    if book is None:
        return error_response(404, "not_found", f"Book {book_id} does not exist.")

    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "invalid_json", "Request body must be valid JSON.")

    cleaned, errors = validate(payload, partial=False)
    if errors:
        return error_response(400, "validation_error", "Book could not be updated.", errors)

    book.apply(cleaned, partial=False)
    db.session.commit()
    return jsonify({"data": book.to_dict()})


# ------------------------------------------------------------------- patch --


@api_bp.patch("/books/<int:book_id>")
def update_book(book_id: int):
    """PATCH = partial update. Only the supplied fields change."""
    book = _get_or_404(book_id)
    if book is None:
        return error_response(404, "not_found", f"Book {book_id} does not exist.")

    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "invalid_json", "Request body must be valid JSON.")
    if not payload:
        return error_response(400, "validation_error",
                              "Empty payload.", {"_body": "send at least one field to update"})

    cleaned, errors = validate(payload, partial=True)
    if errors:
        return error_response(400, "validation_error", "Book could not be updated.", errors)
    if not cleaned:
        return error_response(400, "validation_error",
                              "Nothing to update.", {"_body": "no updatable fields supplied"})

    book.apply(cleaned, partial=True)
    db.session.commit()
    return jsonify({"data": book.to_dict()})


# ------------------------------------------------------------------ delete --


@api_bp.delete("/books/<int:book_id>")
def delete_book(book_id: int):
    book = _get_or_404(book_id)
    if book is None:
        return error_response(404, "not_found", f"Book {book_id} does not exist.")
    db.session.delete(book)
    db.session.commit()
    return "", 204
