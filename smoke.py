"""Smoke test: boots the real server and exercises CRUD over actual HTTP.

pytest covers the app via Flask's test client; this covers the ASGI/WSGI
path, real sockets, status codes and headers. Run with:  python smoke.py
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5099/api/v1"


def call(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else None, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else None, dict(exc.headers)


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{(' -> ' + detail) if detail else ''}")
    return condition


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, "run.py", "--port", "5099"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
    try:
        for _ in range(40):
            time.sleep(0.25)
            status, _, _ = call("GET", "/health")
            if status == 200:
                break
        else:
            print("server never came up")
            return 1

        print("Health")
        status, body, _ = call("GET", "/health")
        ok &= check("GET /health -> 200", status == 200, str(status))
        ok &= check("status field ok", body["status"] == "ok")

        print("Create")
        status, body, headers = call("POST", "/books", {
            "title": "Refactoring", "author": "Martin Fowler",
            "year": 1999, "genre": "Software", "rating": 4.5,
        })
        ok &= check("POST -> 201", status == 201, str(status))
        ok &= check("Location header set",
                    headers.get("Location", "").endswith("/books/1"),
                    headers.get("Location", ""))
        book_id = body["data"]["id"]

        status, body, _ = call("POST", "/books", {"year": 2000})
        ok &= check("POST missing fields -> 400", status == 400, str(status))
        ok &= check("field errors reported",
                    body["error"]["fields"].get("title") == "required",
                    str(body["error"].get("fields")))

        print("Read")
        status, body, _ = call("GET", f"/books/{book_id}")
        ok &= check("GET one -> 200", status == 200 and body["data"]["title"] == "Refactoring")
        status, _, _ = call("GET", "/books/9999")
        ok &= check("GET missing -> 404", status == 404, str(status))
        status, body, _ = call("GET", "/books?q=fowler")
        ok &= check("search q=fowler finds it", body["pagination"]["total"] == 1)
        status, body, _ = call("GET", "/books?sort=bogus")
        ok &= check("bad sort -> 400", status == 400, str(status))

        print("Update")
        status, body, _ = call("PATCH", f"/books/{book_id}", {"rating": 4.9})
        ok &= check("PATCH -> 200", status == 200 and body["data"]["rating"] == 4.9)
        ok &= check("PATCH leaves other fields alone",
                    body["data"]["genre"] == "Software")
        status, body, _ = call("PUT", f"/books/{book_id}",
                               {"title": "Refactoring (2nd ed.)",
                                "author": "Martin Fowler"})
        ok &= check("PUT -> 200", status == 200)
        ok &= check("PUT resets omitted optionals",
                    body["data"]["genre"] is None and body["data"]["rating"] is None)

        print("Delete")
        status, _, _ = call("DELETE", f"/books/{book_id}")
        ok &= check("DELETE -> 204", status == 204, str(status))
        status, _, _ = call("GET", f"/books/{book_id}")
        ok &= check("gone after delete -> 404", status == 404, str(status))

        print("Errors")
        status, body, _ = call("POST", "/books", {"title": "X", "admin": True})
        ok &= check("unknown field -> 400", status == 400, str(status))
        status, body, _ = call("POST", "/health")
        ok &= check("bad method -> 405 JSON", status == 405 and "error" in body)

    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print("\n" + ("ALL SMOKE CHECKS PASSED" if ok else "SMOKE CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
