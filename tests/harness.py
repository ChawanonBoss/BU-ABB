"""
Shared test harness for the BU-ABB Playwright checks in this directory.

Usage pattern for any test script in this folder:

    from harness import serve_repo, new_page

    with serve_repo() as base_url:
        with new_page() as page:
            page.goto(f"{base_url}/index.html")
            page.wait_for_timeout(500)
            page.evaluate("...")  # seed Firestore mock data, sign in, etc.
            ...

Why this exists: earlier ad hoc test scripts each hardcoded their own
`python3 -m http.server <port>` + manual PID cleanup, which meant constantly
picking a free port, sed-replacing it across scripts, and remembering to
`taskkill` the server afterward. `serve_repo()` spins up a ThreadingHTTPServer
on an OS-assigned ephemeral port bound to the repo root, in a background
thread inside this same process, and tears it down automatically when the
`with` block exits — no port bookkeeping, no leftover processes.
"""
import contextlib
import http.server
import os
import threading

from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_mock.js")

with open(MOCK_PATH, encoding="utf-8") as _f:
    MOCK_JS = _f.read()


class _QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # the default per-request stderr logging is just noise for a test run


@contextlib.contextmanager
def serve_repo():
    handler = lambda *a, **kw: _QuietHTTPRequestHandler(*a, directory=REPO_ROOT, **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _install_firebase_mock(page):
    def handle_route(route):
        if "firebasejs" in route.request.url:
            route.fulfill(status=200, content_type="application/javascript", body=MOCK_JS)
        else:
            route.continue_()
    page.route("**/firebasejs/**", handle_route)


@contextlib.contextmanager
def new_page(viewport=None, collect_errors=True):
    """Launches a fresh Chromium page with the Firestore/Auth mock wired up.

    Yields (page, errors) where `errors` is a list that page-level JS
    exceptions get appended to as they happen — check `errors == []` at the
    end of a test rather than only relying on printed output.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=viewport or {"width": 1400, "height": 900})
        errors = []
        if collect_errors:
            page.on("pageerror", lambda e: errors.append(str(e)))
        _install_firebase_mock(page)
        try:
            yield page, errors
        finally:
            browser.close()


SEED_BASIC_ADMIN = """
async () => {
  await db.collection('users').doc('admin1').set({ email:'admin@a.com', name:'Admin', role:'admin' });
  currentUserEmail = 'admin@a.com'; currentUserName = 'Admin'; currentUserUid = 'admin1';
  await onSignedIn();
}
"""


def sign_in_as_admin(page, base_url):
    """Loads index.html and signs in as a bare admin user with no seeded data."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_timeout(500)
    page.evaluate(SEED_BASIC_ADMIN)
    page.wait_for_timeout(600)
