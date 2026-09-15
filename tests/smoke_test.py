"""
General regression smoke test: cold page load, sign in, walk every tab (and the
subtabs that have their own render path), and confirm nothing threw a JS error
and no tab panel got kicked out of `.content` by a stray unclosed <div>
somewhere earlier in the file (see CLAUDE.md "Known gotchas / fragile spots").

Run with: python3 tests/smoke_test.py
"""
import sys

from harness import serve_repo, new_page, sign_in_as_admin

TABS = [
    "dashboard", "orders", "warranty", "cancelled", "customers",
    "promotions", "users", "audit", "trash",
]

SEED_SAMPLE_DATA = """
async () => {
  await db.collection('users').doc('alice1').set({ email:'alice@a.com', name:'Alice', role:'user' });
  await db.collection('orders').doc('o1').set({ so:'A1', customer:'Cust A1', product:'X', price:1000, date:'2026-01-05', shipDate:'2026-01-10', status:'done', po:'INV001', createdBy:'admin1' });
  await db.collection('orders').doc('o2').set({ so:'A2', customer:'Cust A1', product:'Y', price:2000, date:'2025-06-05', status:'cancelled', createdBy:'admin1' });
  await db.collection('customers').doc('c1').set({ name:'Cust A1', createdBy:'admin1' });
  await db.collection('promotions').doc('p1').set({ name:'Promo Sep', month:8, year:2026, giftLabel:'Tote bag', createdBy:'admin1' });
  await db.collection('auditLog').doc('a1').set({ action:'สร้างคำสั่งซื้อ', entityLabel:'A1', details:'', changedBy:'admin1', changedByName:'Admin', timestamp: new Date().toISOString() });
  await db.collection('errorLog').doc('e1').set({ message:'Test error', stack:'', page:'orders', userName:'Admin', timestamp: new Date().toISOString(), severity:'major' });
}
"""


def main():
    with serve_repo() as base_url:
        # Cold load, no sign-in yet: catches temporal-dead-zone crashes where a top-level
        # `let`/`const` further down the script gets referenced by code that can run early
        # (e.g. the auth listener's signed-out branch) — has bitten this project twice before.
        with new_page() as (page, errors):
            page.goto(f"{base_url}/index.html")
            page.wait_for_timeout(800)
            assert errors == [], f"Cold load threw JS error(s) before any sign-in: {errors}"

        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_SAMPLE_DATA)
            page.wait_for_timeout(400)

            for tab in TABS:
                page.evaluate(f"() => showTab('{tab}')")
                page.wait_for_timeout(200)

            misparented = page.evaluate(
                "() => Array.from(document.querySelectorAll('.tab-panel'))"
                ".filter(p => !p.parentElement.classList.contains('content')).map(p => p.id)"
            )
            assert misparented == [], (
                f"Tab panel(s) got kicked out of .content — a <div> is unbalanced "
                f"somewhere earlier in index.html: {misparented}"
            )
            assert errors == [], f"Page threw JS error(s) during the tab sweep: {errors}"

    print("smoke_test: OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"smoke_test: FAILED — {e}", file=sys.stderr)
        sys.exit(1)
