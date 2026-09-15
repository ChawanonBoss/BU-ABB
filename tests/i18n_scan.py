"""
Toggles the app to English and scans every tab (plus a couple of dynamic
states — the Orders "customer not found" banner, Dashboard's shipped subtab)
for any leftover Thai-Unicode-range text in text nodes or placeholder/title
attributes. See CLAUDE.md "Language toggle" for the two recurring bug shapes
this catches: a dynamically-rendered string that was never wrapped in t(),
and a table whose data only re-renders via a Firestore listener rather than
on every tab switch (so it can go stale-language until something else
happens to redraw it).

Deliberately ignores: the Baht sign ฿ (technically inside the Thai Unicode
block, not actually Thai text) and "ไทย" (the language toggle's own label,
which correctly shows the *other* language's name).

Run with: python3 tests/i18n_scan.py
"""
import re
import sys

from harness import serve_repo, new_page, sign_in_as_admin

THAI_RE = re.compile(r"[฀-๿]")
IGNORE = {"฿", "ไทย"}

SEED = """
async () => {
  await db.collection('orders').doc('o1').set({ so:'A1', customer:'Cust A1', product:'X', price:1000, date:'2026-01-05', shipDate:'2026-01-10', status:'done', po:'INV001', createdBy:'admin1', warrantyMonths:12 });
  await db.collection('customers').doc('c1').set({ name:'Cust A1', createdBy:'admin1' });
  await db.collection('promotions').doc('p1').set({ name:'Promo Sep', month:8, year:2026, giftLabel:'Tote bag', createdBy:'admin1' });
  await db.collection('auditLog').doc('a1').set({ action:'สร้างคำสั่งซื้อ', entityLabel:'A1', details:'', changedBy:'admin1', changedByName:'Admin', timestamp: new Date().toISOString() });
  await db.collection('errorLog').doc('e1').set({ message:'Test error', stack:'', page:'orders', userName:'Admin', timestamp: new Date().toISOString(), severity:'major' });
}
"""

SCAN_JS = """
() => {
  const out = [];
  const isVisible = (el) => {
    if (el.tagName === 'OPTION') {
      const container = el.closest('.tab-panel, .modal-overlay') || el.closest('select');
      if (!container) return true;
      if (container.tagName === 'SELECT') return container.checkVisibility ? container.checkVisibility() : true;
      return getComputedStyle(container).display !== 'none';
    }
    return el.checkVisibility ? el.checkVisibility() : (el.offsetParent !== null);
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while (n = walker.nextNode()) {
    const p = n.parentElement;
    if (!p || p.closest('script,style')) continue;
    if (!isVisible(p)) continue;
    const v = n.nodeValue.trim();
    if (v) out.push('[text] ' + v);
  }
  document.querySelectorAll('[placeholder]').forEach(el => {
    if (!isVisible(el)) return;
    const v = el.getAttribute('placeholder');
    if (v) out.push('[placeholder] ' + v);
  });
  document.querySelectorAll('[title]').forEach(el => {
    if (!isVisible(el)) return;
    const v = el.getAttribute('title');
    if (v) out.push('[title] ' + v);
  });
  return out;
}
"""

TABS = ["dashboard", "orders", "warranty", "cancelled", "customers", "promotions", "users", "audit", "trash"]


def leftover_thai(texts):
    found = []
    for entry in texts:
        value = entry.split("] ", 1)[1] if "] " in entry else entry
        if value in IGNORE:
            continue
        # A Baht-formatted amount like "฿1,000" is a currency symbol plus digits, not
        # translatable text — the ฿ sign itself sits inside the Thai Unicode block, so strip
        # it out before testing rather than only ignoring the bare symbol on its own.
        stripped = value.replace("฿", "")
        if THAI_RE.search(stripped):
            found.append(entry)
    return found


def main():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED)
            page.wait_for_timeout(400)

            page.click("#railMenuBtn")
            page.wait_for_timeout(150)
            page.click("#langToggleBtn")
            page.wait_for_timeout(200)

            failures = {}
            for tab in TABS:
                page.evaluate(f"() => showTab('{tab}')")
                page.wait_for_timeout(250)
                leftover = leftover_thai(page.evaluate(SCAN_JS))
                if leftover:
                    failures[tab] = leftover

            assert errors == [], f"Page threw JS error(s) during the i18n scan: {errors}"
            assert not failures, "Leftover Thai text found while in English mode:\n" + "\n".join(
                f"  {tab}: {items}" for tab, items in failures.items()
            )

    print("i18n_scan: OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"i18n_scan: FAILED — {e}", file=sys.stderr)
        sys.exit(1)
