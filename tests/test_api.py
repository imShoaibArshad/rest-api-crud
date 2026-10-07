"""End-to-end tests for the Books API.

Uses an in-memory SQLite database per test session so nothing touches the
dev file, and covers the cases that actually break APIs in production:
bad types, unknown fields, missing required fields, 404s, pagination
stability, and the PUT-vs-PATCH distinction.
"""

import pytest

from app import create_app, db
from app.models import Book


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample(app):
    """A couple of rows, committed inside the app context."""
    rows = [
        Book(title="Clean Code", author="Robert C. Martin",
             year=2008, genre="Software", rating=4.3),
        Book(title="The Art of Statistics", author="David Spiegelhalter",
             year=2019, genre="Statistics", rating=4.6),
    ]
    db.session.add_all(rows)
    db.session.commit()
    return rows


VALID = {"title": "Refactoring", "author": "Martin Fowler",
         "year": 1999, "genre": "Software", "rating": 4.5}


def json_of(resp):
    return resp.get_json()


# ------------------------------------------------------------------ health --


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert json_of(resp)["status"] == "ok"


# ----------------------------------------------------------------- read -----


def test_list_empty(client):
    resp = client.get("/api/v1/books")
    assert resp.status_code == 200
    body = json_of(resp)
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


def test_list_returns_rows(client, sample):
    body = json_of(client.get("/api/v1/books"))
    assert body["pagination"]["total"] == 2
    assert {b["title"] for b in body["data"]} == {"Clean Code", "The Art of Statistics"}


def test_get_single(client, sample):
    resp = client.get(f"/api/v1/books/{sample[0].id}")
    assert resp.status_code == 200
    assert json_of(resp)["data"]["title"] == "Clean Code"


def test_get_missing_returns_404_json(client):
    resp = client.get("/api/v1/books/9999")
    assert resp.status_code == 404
    body = json_of(resp)
    assert body["error"]["code"] == "not_found"
    # Errors must be JSON, not Flask's HTML page.
    assert resp.content_type.startswith("application/json")


def test_list_filter_by_genre(client, sample):
    body = json_of(client.get("/api/v1/books?genre=Statistics"))
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["author"] == "David Spiegelhalter"


def test_list_search_q(client, sample):
    body = json_of(client.get("/api/v1/books?q=fowler"))
    assert body["pagination"]["total"] == 0  # not present yet
    body = json_of(client.get("/api/v1/books?q=statistics"))
    assert body["pagination"]["total"] == 1


def test_list_sort_desc(client, sample):
    body = json_of(client.get("/api/v1/books?sort=year&order=desc"))
    assert [b["year"] for b in body["data"]] == [2019, 2008]


def test_list_rejects_bad_sort(client):
    resp = client.get("/api/v1/books?sort=password")
    assert resp.status_code == 400
    assert "sort" in json_of(resp)["error"]["fields"]


def test_list_rejects_bad_per_page(client):
    resp = client.get("/api/v1/books?per_page=9999")
    assert resp.status_code == 400
    assert "per_page" in json_of(resp)["error"]["fields"]


# --------------------------------------------------------------- create -----


def test_create_returns_201_and_location(client):
    resp = client.post("/api/v1/books", json=VALID)
    assert resp.status_code == 201
    assert resp.headers["Location"].endswith("/api/v1/books/1")
    body = json_of(resp)
    assert body["data"]["title"] == "Refactoring"
    assert body["data"]["available"] is True
    assert "created_at" in body["data"]


def test_create_requires_title_and_author(client):
    resp = client.post("/api/v1/books", json={"year": 2000})
    assert resp.status_code == 400
    fields = json_of(resp)["error"]["fields"]
    assert fields["title"] == "required"
    assert fields["author"] == "required"


def test_create_rejects_unknown_field(client):
    resp = client.post("/api/v1/books", json={**VALID, "admin": True})
    assert resp.status_code == 400
    assert "unknown field" in json_of(resp)["error"]["fields"]["_body"]


def test_create_rejects_out_of_range_rating(client):
    resp = client.post("/api/v1/books", json={**VALID, "rating": 11})
    assert resp.status_code == 400
    assert "rating" in json_of(resp)["error"]["fields"]


def test_create_rejects_string_year(client):
    resp = client.post("/api/v1/books", json={**VALID, "year": "nineteen"})
    assert resp.status_code == 400
    assert "year" in json_of(resp)["error"]["fields"]


def test_create_rejects_non_json_body(client):
    resp = client.post("/api/v1/books", data="title=Refactoring",
                       content_type="text/plain")
    assert resp.status_code == 400
    assert json_of(resp)["error"]["code"] in ("invalid_json", "unsupported_media_type")


def test_create_strips_whitespace(client):
    resp = client.post("/api/v1/books", json={"title": "   Clean Code   ",
                                              "author": "  Bob  "})
    assert resp.status_code == 201
    assert json_of(resp)["data"]["title"] == "Clean Code"
    assert json_of(resp)["data"]["author"] == "Bob"


# ------------------------------------------------------------------ put -----


def test_put_replaces_whole_record(client, sample):
    book_id = sample[0].id
    resp = client.put(f"/api/v1/books/{book_id}",
                      json={"title": "Clean Code (2nd ed.)",
                            "author": "Robert C. Martin",
                            "year": 2008, "genre": "Software", "rating": 4.8})
    assert resp.status_code == 200
    body = json_of(resp)["data"]
    assert body["title"] == "Clean Code (2nd ed.)"
    assert body["rating"] == 4.8


def test_put_requires_all_required_fields(client, sample):
    book_id = sample[0].id
    resp = client.put(f"/api/v1/books/{book_id}", json={"title": "Only a title"})
    assert resp.status_code == 400
    assert "author" in json_of(resp)["error"]["fields"]


def test_put_clears_optional_fields_not_sent(client, sample):
    """PUT is a full replacement: an omitted optional field resets."""
    book_id = sample[0].id
    resp = client.put(f"/api/v1/books/{book_id}",
                      json={"title": "Clean Code", "author": "Robert C. Martin"})
    assert resp.status_code == 200
    assert json_of(resp)["data"]["genre"] is None
    assert json_of(resp)["data"]["rating"] is None


def test_put_missing_404(client):
    resp = client.put("/api/v1/books/4242", json=VALID)
    assert resp.status_code == 404


# ---------------------------------------------------------------- patch -----


def test_patch_updates_only_supplied_fields(client, sample):
    book_id = sample[0].id
    resp = client.patch(f"/api/v1/books/{book_id}", json={"rating": 5.0})
    assert resp.status_code == 200
    body = json_of(resp)["data"]
    assert body["rating"] == 5.0
    assert body["title"] == "Clean Code"       # untouched
    assert body["genre"] == "Software"         # untouched


def test_patch_does_not_clear_unsent_fields(client, sample):
    """The key difference from PUT — this is the bug worth testing for."""
    book_id = sample[0].id
    resp = client.patch(f"/api/v1/books/{book_id}", json={"title": "Clean Code v2"})
    assert resp.status_code == 200
    body = json_of(resp)["data"]
    assert body["genre"] == "Software"
    assert body["rating"] == 4.3


def test_patch_empty_payload_rejected(client, sample):
    resp = client.patch(f"/api/v1/books/{sample[0].id}", json={})
    assert resp.status_code == 400


def test_patch_invalid_value_rejected(client, sample):
    resp = client.patch(f"/api/v1/books/{sample[0].id}", json={"rating": -3})
    assert resp.status_code == 400
    assert "rating" in json_of(resp)["error"]["fields"]


# --------------------------------------------------------------- delete -----


def test_delete_returns_204_then_404(client, app, sample):
    book_id = sample[0].id
    assert client.delete(f"/api/v1/books/{book_id}").status_code == 204
    # Row is really gone.
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404
    with app.app_context():
        assert db.session.get(Book, book_id) is None


def test_delete_missing_404(client):
    assert client.delete("/api/v1/books/9999").status_code == 404


# ------------------------------------------------------------- method 405 ---


def test_unsupported_method_is_json_405(client):
    resp = client.post("/api/v1/health")
    assert resp.status_code == 405
    assert json_of(resp)["error"]["code"] == "method_not_allowed"


# ------------------------------------------------------------- pagination ----


def test_pagination_is_stable_across_pages(client, app):
    with app.app_context():
        db.session.add_all(
            Book(title=f"Book {i}", author="Author", year=2000 + i) for i in range(25)
        )
        db.session.commit()

    seen = []
    page = 1
    while True:
        body = json_of(client.get(f"/api/v1/books?page={page}&per_page=10&sort=year&order=asc"))
        if not body["data"]:
            break
        seen.extend(b["id"] for b in body["data"])
        if not body["pagination"]["has_next"]:
            break
        page += 1

    # No duplicates, no gaps.
    assert len(seen) == 25
    assert len(set(seen)) == 25
