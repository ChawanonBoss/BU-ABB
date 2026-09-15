# Playwright regression tests

A small, persisted set of checks for `index.html` — kept here instead of being
rewritten from scratch as throwaway scripts every time the app gets touched.

## Setup (once)

```
pip install playwright
python -m playwright install chromium
```

## Running

```
cd tests
python3 run_all.py          # everything
python3 smoke_test.py       # cold load + walk every tab, no JS errors, no misparented tab panels
python3 i18n_scan.py        # English mode shouldn't leave any Thai text on screen
python3 features_test.py    # specific behaviors that broke once already (see CLAUDE.md)
```

Each script is self-contained: it starts its own local HTTP server (bound to
an OS-assigned free port, torn down automatically) and drives a real headless
Chromium via Playwright against `../index.html`, with `firebase_mock.js`
standing in for the real Firebase SDK — see `harness.py` for the shared
plumbing (`serve_repo()`, `new_page()`, `sign_in_as_admin()`).

## Why a mock instead of real Firebase

The real app requires network access to Google's CDN and a signed-in Firebase
session; these tests instead intercept `**/firebasejs/**` and serve
`firebase_mock.js`, an in-memory reactive Firestore substitute (`.where()`,
`.orderBy()`, `.startAfter()`, `.limit()`, `.batch()`,
`FieldValue.delete()`, and change-notifying `onSnapshot()` on both
collections and single docs). This means:

- No real Firebase project/credentials/network needed to run these.
- Test data lives only in the page's own JS memory for the duration of one
  browser instance — nothing is ever written to the real production database.
- `window.currentUserRole`/`currentUserUid`/etc. must be set as **bare**
  identifiers inside `page.evaluate(...)`, not `window.foo = ...` — they're
  top-level `let` bindings in a classic (non-module) `<script>`, not
  `window` properties. See CLAUDE.md's "For visual verification" bullet.

## When to add a new check

If you fix a bug that wasn't obvious from just reading the code (something
that needed an actual browser to notice — a silent no-op, a class that never
gets added, a value that resolves to the wrong type), add a case to
`features_test.py` rather than only verifying it by hand once. That's how
every existing check here came to exist — each one previously bit the app for
real. `smoke_test.py` and `i18n_scan.py` are meant to stay broad/generic;
put anything specific to one feature in `features_test.py` instead.
