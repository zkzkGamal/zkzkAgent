"""T4 check: does the calculator app the agent wrote actually work?

    python3 -E benchmark/check_app.py <project_dir>

tasks.py starts this in its own process with a 60 s timeout, because it
imports model-written code. It prints ONE JSON object of named checks on its
last stdout line; T4 passes only when all of them are true:

    {"files_exist": true, "get_root": true, "calculates": true, "rejects_code": true}

- files_exist:  app.py, static/index.html and requirements.txt exist
- get_root:     GET / returns 200
- calculates:   POST /api/calculate {"expression": "2+3*4"} returns 200 and result == 14
- rejects_code: POST /api/calculate {"expression": "__import__('os').getcwd()"}
                does NOT return 200 with a result (an app built on eval() fails this)

-E (not -I) because -I also hides user site-packages, where FastAPI may live.
"""

import json
import os
import pathlib
import sys

REQUIRED_FILES = ["app.py", "static/index.html", "requirements.txt"]
CALC_EXPRESSION = "2+3*4"
CALC_RESULT = 14
INJECTION = "__import__('os').getcwd()"


def _post_expression(client, expression: str):
    """Return (status_code, json_body), or (None, None) if the request blew up."""
    try:
        response = client.post("/api/calculate", json={"expression": expression})
    except Exception as exc:  # noqa: BLE001 — model-written code can fail any way
        print(f"[CHECK] POST {expression!r} raised {exc!r}", file=sys.stderr)
        return None, None
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _result_of(body) -> object:
    return body.get("result") if isinstance(body, dict) else None


def check(project: pathlib.Path) -> dict:
    results = {"files_exist": False, "get_root": False, "calculates": False, "rejects_code": False}
    if not project.is_dir():
        print(f"[CHECK] {project} does not exist", file=sys.stderr)
        return results
    results["files_exist"] = all((project / name).is_file() for name in REQUIRED_FILES)

    # Put the project folder first on sys.path, so `import app` loads the
    # agent-written <project>/app.py (it is not a module in this repo). chdir
    # too: generated apps often use relative paths like StaticFiles(directory="static")
    sys.path.insert(0, str(project))
    os.chdir(project)
    try:
        from fastapi.testclient import TestClient

        from app import app as generated_app  # the FastAPI() instance in <project>/app.py

        client = TestClient(generated_app, raise_server_exceptions=False)  # crashes become 500s
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"[CHECK] could not load the app: {exc!r}", file=sys.stderr)
        return results

    try:
        results["get_root"] = client.get("/").status_code == 200
    except Exception as exc:  # noqa: BLE001
        print(f"[CHECK] GET / raised {exc!r}", file=sys.stderr)

    status, body = _post_expression(client, CALC_EXPRESSION)
    try:
        results["calculates"] = status == 200 and float(_result_of(body)) == CALC_RESULT
    except (TypeError, ValueError):
        results["calculates"] = False

    status, body = _post_expression(client, INJECTION)
    results["rejects_code"] = status is not None and not (
        status == 200 and _result_of(body) is not None
    )
    return results


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 -E benchmark/check_app.py <project_dir>", file=sys.stderr)
        return 2
    results = check(pathlib.Path(sys.argv[1]).resolve())
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
