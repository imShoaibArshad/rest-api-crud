"""Payload validation.

Hand-rolled instead of marshmallow/werkzeug's validator so the rules are
readable and the error messages can be as specific as the client needs.
Every failure returns 400 with a `fields` map: {"field": "message"}.
"""

STRIPPED = ("title", "author", "genre")
MAX_LEN = {"title": 200, "author": 120, "genre": 60}

REQUIRED = ("title", "author")
OPTIONAL = ("year", "genre", "rating", "available")
ALLOWED = set(REQUIRED) | set(OPTIONAL)


def validate(payload, partial: bool) -> tuple[dict, dict[str, str]]:
    """Return (cleaned_fields, errors). `errors` empty means valid."""
    errors: dict[str, str] = {}
    cleaned: dict = {}

    if not isinstance(payload, dict):
        return {}, {"_body": "JSON object expected, e.g. {\"title\": \"...\"}"}

    unknown = sorted(set(payload) - ALLOWED)
    if unknown:
        errors["_body"] = (
            f"unknown field(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(ALLOWED))}"
        )

    if not partial:
        for field in REQUIRED:
            if field not in payload or payload[field] in ("", None):
                errors[field] = "required"

    for field in STRIPPED:
        if field in payload:
            value = payload[field]
            if value is None:
                if field in REQUIRED:
                    errors.setdefault(field, "required")
                continue
            if not isinstance(value, str):
                errors[field] = "must be a string"
                continue
            value = value.strip()
            if not value and field in REQUIRED:
                errors[field] = "cannot be blank"
                continue
            if len(value) > MAX_LEN[field]:
                errors[field] = f"max {MAX_LEN[field]} characters"
                continue
            cleaned[field] = value

    if "year" in payload:
        value = payload["year"]
        if value is None:
            cleaned["year"] = None
        elif isinstance(value, bool) or not isinstance(value, int):
            errors["year"] = "must be an integer (or null)"
        elif not 1450 <= value <= 2100:
            errors["year"] = "must be between 1450 and 2100"
        else:
            cleaned["year"] = value

    if "rating" in payload:
        value = payload["rating"]
        if value is None:
            cleaned["rating"] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            errors["rating"] = "must be a number between 0 and 5 (or null)"
        elif not 0 <= float(value) <= 5:
            errors["rating"] = "must be between 0 and 5"
        else:
            cleaned["rating"] = float(value)

    if "available" in payload:
        value = payload["available"]
        if not isinstance(value, bool):
            errors["available"] = "must be true or false"
        else:
            cleaned["available"] = value

    return cleaned, errors
