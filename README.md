# Books REST API

A Flask + SQLAlchemy CRUD API with **validation, pagination, filtering and
consistent JSON errors** — plus a 29-test pytest suite and an HTTP smoke test.

Endpoints are the part of backend work that looks simple and breaks in
interesting ways, so this one handles the cases that actually cause outages:
bad types, unknown fields, missing required fields, unstable pagination, and
the PUT-vs-PATCH distinction.

## Endpoints

Base URL: `http://127.0.0.1:5000/api/v1`

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| GET | `/health` | liveness probe | `200` |
| GET | `/books` | list (paginated / filterable) | `200` |
| GET | `/books/{id}` | fetch one | `200` |
| POST | `/books` | create | `201` + `Location` |
| PUT | `/books/{id}` | **full replacement** | `200` |
| PATCH | `/books/{id}` | **partial update** | `200` |
| DELETE | `/books/{id}` | delete | `204` no body |

### List query parameters

| Param | Example | Notes |
| --- | --- | --- |
| `page`, `per_page` | `?page=2&per_page=20` | `per_page` capped at 100 |
| `q` | `?q=fowler` | free-text over title / author / genre |
| `genre`, `author` | `?genre=Software` | `genre` exact (case-insensitive), `author` substring |
| `year` | `?year=1999` | exact |
| `available` | `?available=false` | `true`/`false`/`1`/`0` |
| `sort`, `order` | `?sort=year&order=desc` | allow-listed columns only |

Response envelope:

```json
{
  "data": [ ... ],
  "pagination": { "page": 1, "per_page": 20, "total": 25, "pages": 2,
                  "has_next": true, "has_prev": false,
                  "next": "/api/v1/books?page=2&per_page=20", "prev": null }
}
```

## Error shape

Every failure — including Flask's own 404/405 — returns JSON:

```json
{ "error": { "code": "validation_error",
             "message": "Book could not be created.",
             "fields": { "title": "required", "rating": "must be between 0 and 5" } } }
```

No stack traces ever reach the client (`handle_unexpected` rolls the session
back and returns a generic 500).

## The PUT vs PATCH distinction

This is the part most CRUD APIs get wrong, so it's pinned by tests:

```bash
# PATCH rating only -> title, author, genre untouched
curl -X PATCH .../books/1 -d '{"rating": 4.9}'

# PUT is a full replacement -> genre/rating NOT sent means RESET to null
curl -X PUT .../books/1 -d '{"title": "Refactoring", "author": "Martin Fowler"}
```

`test_patch_does_not_clear_unsent_fields` and
`test_put_clears_optional_fields_not_sent` exist specifically to catch a
regression where both verbs behave the same.

## Running it

```bash
pip install -r requirements.txt
python run.py --seed        # insert 5 sample rows
python run.py               # serve on http://127.0.0.1:5000
```

## Testing

```bash
python -m pytest tests -q   # 29 tests, in-memory SQLite
python smoke.py             # boots the real server, 18 checks over HTTP
```

- **pytest** uses `create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})`
  so tests never touch the dev database, and each test drops/creates its schema.
- **`smoke.py`** covers what the test client can't: real sockets, the WSGI
  path, status lines and response headers.

## Design decisions

- **App factory (`create_app`)** — tests get an isolated app; no global
  singleton, no import-order surprises.
- **Hand-rolled validation** (`app/validation.py`) instead of a schema library —
  the rules and their error messages stay readable in ~90 lines.
- **Allow-listed sort columns** — sorting on an arbitrary client string is a
  common SQL-injection / 500 vector.
- **Secondary sort on `id`** — without it, rows with tied sort keys can repeat
  or vanish across pages. Pinned by `test_pagination_is_stable_across_pages`.
- **Server-assigned IDs** — client-supplied `id` is rejected as an unknown field.
- **SQLAlchemy 2.x `Mapped`/`mapped_column`** with `CheckConstraint`s for
  `year` (1450–2100) and `rating` (0–5), enforced at the DB level too.

## Schema

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | int | PK, auto |
| `title` | string(200) | required, trimmed |
| `author` | string(120) | required, trimmed |
| `year` | int | nullable, 1450–2100 |
| `genre` | string(60) | nullable |
| `rating` | float | nullable, 0–5 |
| `available` | bool | default `true` |
| `created_at` / `updated_at` | datetime | UTC, `updated_at` auto-touches |

Indexes on `author` and `genre` (both filter/sort targets).

## Limitations

- **No authentication** — anyone can write. Adding JWT/API-key auth is the
  obvious next step.
- **No `updated_at`-based concurrency** — no `If-Match`/ETag support, so
  last-write-wins under concurrent edits.
- **SQLite only** — fine for this scope; `DATABASE_URL` is read from the
  environment, so Postgres needs no code change.
- **No rate limiting or CORS.**
- `ilike` on SQLite is a case-insensitive `LIKE`, not a real case-folded
  comparison — it will behave differently on Postgres.

## Project layout

```
rest-api-crud/
├── run.py               # CLI: --host --port --debug --seed
├── smoke.py             # end-to-end HTTP checks against the real server
├── app/
│   ├── __init__.py      # create_app factory, db wiring
│   ├── models.py        # Book model + to_dict/apply
│   ├── validation.py    # payload rules + field-level error messages
│   ├── routes.py        # CRUD + list/filter/sort/paginate
│   └── errors.py        # uniform JSON error responses
├── tests/test_api.py    # 29 tests
└── docs/postman_collection.json
```

## Tech

Python · Flask · SQLAlchemy 2.x · Flask-SQLAlchemy · pytest
