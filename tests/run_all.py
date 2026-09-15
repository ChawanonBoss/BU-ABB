"""
Runs every test module in this directory and reports a pass/fail summary.
Each module is run in-process (not as a subprocess) so failures share one
Playwright/browser startup cost; a module's own main()/asserts still isolate
its checks from the others.

Run with: python3 tests/run_all.py
"""
import sys
import traceback

import features_test
import i18n_scan
import smoke_test

MODULES = [smoke_test, i18n_scan, features_test]


def main():
    failed = []
    for mod in MODULES:
        try:
            mod.main()
        except SystemExit as e:
            if e.code:
                failed.append(mod.__name__)
        except AssertionError:
            print(f"{mod.__name__}: FAILED", file=sys.stderr)
            traceback.print_exc()
            failed.append(mod.__name__)

    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    print("All test modules passed.")


if __name__ == "__main__":
    main()
