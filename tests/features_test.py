"""
Feature-specific regression checks for behaviors that were tricky enough to
get wrong once already. Each function is independent (fresh page/browser),
so a failure in one doesn't hide the others. See CLAUDE.md for the "why"
behind each of these.

Run with: python3 tests/features_test.py
"""
import sys

from harness import serve_repo, new_page, sign_in_as_admin

SEED_ONE_ORDER = """
async () => {
  await db.collection('orders').doc('o1').set({ so:'A1', customer:'Cust A1', product:'X', price:1000, date:'2026-01-05', shipDate:'2026-01-10', status:'done', po:'INV001', createdBy:'admin1' });
  await db.collection('customers').doc('c1').set({ name:'Cust A1', createdBy:'admin1' });
}
"""


def check_order_date_and_price_inline_edit():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_ONE_ORDER)
            page.wait_for_timeout(400)
            page.evaluate("() => showTab('orders')")
            page.wait_for_timeout(300)

            # order date: editing to a real date saves; clearing it is rejected and reverted
            page.evaluate("""
                () => {
                  const input = document.querySelectorAll('#ordersBody tr input[type=date]')[0];
                  input.value = '2026-02-20';
                  input.dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(200)
            new_date = page.evaluate("() => data.orders.find(o=>o.id==='o1').date")
            assert new_date == "2026-02-20", f"order date inline edit didn't save, got {new_date!r}"

            page.evaluate("""
                () => {
                  const input = document.querySelectorAll('#ordersBody tr input[type=date]')[0];
                  input.value = '';
                  input.dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(200)
            after_clear = page.evaluate("() => data.orders.find(o=>o.id==='o1').date")
            assert after_clear == "2026-02-20", "clearing order date should be rejected, not saved as empty"

            # price: typed value is live comma-formatted and parsed back to a plain number on save
            page.evaluate("""
                () => {
                  const input = document.querySelector('#ordersBody tr .inline-input');
                  input.value = '2500.50';
                  input.dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(200)
            price = page.evaluate("() => data.orders.find(o=>o.id==='o1').price")
            assert price == 2500.5 and isinstance(price, float), f"order price inline edit gave {price!r}"

            assert errors == [], f"JS error(s) during order inline-edit check: {errors}"
    print("check_order_date_and_price_inline_edit: OK")


def check_orders_animation_plays_once():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_ONE_ORDER)
            page.wait_for_timeout(400)

            page.evaluate("() => showTab('orders')")
            has_class_on_open = page.evaluate(
                "() => document.getElementById('ordersBody').classList.contains('rows-animate-in')"
            )
            assert has_class_on_open, "opening the Orders tab should arm the row fade-in animation"

            page.wait_for_timeout(700)
            has_class_after_delay = page.evaluate(
                "() => document.getElementById('ordersBody').classList.contains('rows-animate-in')"
            )
            assert not has_class_after_delay, "animation class should be removed ~500ms after tab-open"

            # an inline edit re-renders the table (via the live listener) but must NOT replay it
            page.evaluate("""
                () => {
                  const input = document.querySelector('#ordersBody tr .inline-input');
                  input.value = '5000';
                  input.dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(300)
            has_class_after_edit = page.evaluate(
                "() => document.getElementById('ordersBody').classList.contains('rows-animate-in')"
            )
            assert not has_class_after_edit, "saving a field must not replay the row fade-in animation"

            assert errors == [], f"JS error(s) during animation check: {errors}"
    print("check_orders_animation_plays_once: OK")


def check_sign_out_hides_person_filter():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            visible_signed_in = page.evaluate(
                "() => getComputedStyle(document.getElementById('targetUserFilter')).display"
            )
            assert visible_signed_in != "none", "admin should see the person filter while signed in"

            page.evaluate("() => auth.signOut()")
            page.wait_for_timeout(300)
            display_after_signout = page.evaluate(
                "() => document.getElementById('targetUserFilter').style.display"
            )
            assert display_after_signout == "none", (
                "person filter must be explicitly hidden on sign-out, not left over from the "
                "previous admin session on top of the login screen"
            )
            assert errors == [], f"JS error(s) during sign-out check: {errors}"
    print("check_sign_out_hides_person_filter: OK")


def check_trash_purge_banner_and_bulk_delete():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("""
                async () => {
                  await db.collection('orders').doc('o1').set({ so:'A1', customer:'Cust A1', product:'X', price:1000, date:'2026-01-05', status:'cancelled', createdBy:'admin1', deletedAt:'2025-01-01T00:00:00.000Z', deletedBy:'admin1' });
                  await db.collection('orders').doc('o2').set({ so:'A2', customer:'Cust A2', product:'Y', price:2000, date:'2026-01-05', status:'cancelled', createdBy:'admin1', deletedAt: new Date().toISOString(), deletedBy:'admin1' });
                }
            """)
            page.wait_for_timeout(300)
            page.evaluate("() => showTab('trash')")
            page.click("#trashRefreshBtn")
            page.wait_for_timeout(400)

            banner_visible = page.evaluate("() => document.getElementById('trashPurgeBanner').style.display")
            assert banner_visible == "flex", "purge banner should appear when an item is older than the threshold"

            page.click("#trashPurgeBtn")
            page.wait_for_timeout(200)
            page.click("#confirmModalOkBtn")
            page.wait_for_timeout(400)

            remaining = page.evaluate("() => [...__mockStore.orders.keys()]")
            assert remaining == ["o2"], f"purge should only delete the item older than the threshold, got {remaining}"

            banner_after = page.evaluate("() => document.getElementById('trashPurgeBanner').style.display")
            assert banner_after == "none", "banner should hide once nothing old is left"

            assert errors == [], f"JS error(s) during trash purge check: {errors}"
    print("check_trash_purge_banner_and_bulk_delete: OK")


def check_commission_config_anchor_guard():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)

            # The default bracket table must still reproduce both real, already-paid quarters —
            # see CLAUDE.md "Commission calculator" for where these two numbers come from.
            anchors = page.evaluate("""
                () => COMMISSION_KNOWN_ANCHORS.map(a => {
                  const r = calcCommissionForConfig(DEFAULT_COMMISSION_CONFIG, a.shipped, a.gp, a.target);
                  return { label: a.label, expected: a.expected, actual: r.amount };
                })
            """)
            for a in anchors:
                assert abs(a["actual"] - a["expected"]) < 1, (
                    f"DEFAULT_COMMISSION_CONFIG no longer reproduces {a['label']}: "
                    f"expected {a['expected']}, got {a['actual']}"
                )

            # Editing a bracket that both anchors fall into must surface a confirmation warning
            # before saving, rather than silently overwriting the config.
            page.evaluate("""
                () => {
                  openCommissionSettingsModal();
                  commissionConfigDraft.gpBrackets[9].rate = 5.0; // 18-20% GP bracket, used by both anchors
                }
            """)
            page.click("#commissionSettingsSaveBtn")
            page.wait_for_timeout(200)
            confirm_visible = page.evaluate("() => document.getElementById('confirmModal').style.display")
            assert confirm_visible == "flex", "breaking a known anchor payout must prompt for confirmation"

            page.click("#confirmModalCancelBtn")
            page.wait_for_timeout(200)
            settings_still_open = page.evaluate(
                "() => document.getElementById('commissionSettingsModal').style.display"
            )
            assert settings_still_open == "flex", "cancelling the warning must not close the settings modal"
            saved_after_cancel = page.evaluate("() => __mockStore.commissionConfig")
            assert not saved_after_cancel, "cancelling the warning must not write anything to Firestore"

            assert errors == [], f"JS error(s) during commission anchor guard check: {errors}"
    print("check_commission_config_anchor_guard: OK")


def check_gp_target_is_a_locked_constant():
    # Target GP% is a fixed company policy (confirmed explicitly), not per-person/editable —
    # shown as a static sub-line under the "GP (%)" stat card. See CLAUDE.md "Commission
    # calculator". This replaced an earlier editable-per-person version of this field.
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("() => showTab('dashboard')")
            page.wait_for_timeout(150)
            page.evaluate("() => document.querySelector('[data-dashsub=\"shipped\"]').click()")
            page.wait_for_timeout(200)

            gp_card_text = page.evaluate(
                "() => document.getElementById('statGPPercent').closest('.stat-card').textContent"
            )
            assert "20%" in gp_card_text, f"GP (%) card should show the locked 20% target, got {gp_card_text!r}"
            assert not page.evaluate("() => !!document.querySelector('.stat-value-input')"), (
                "target GP% must not be an editable input anywhere — it's a locked constant now"
            )

            assert errors == [], f"JS error(s) during GP target constant check: {errors}"
    print("check_gp_target_is_a_locked_constant: OK")


def check_dark_mode_soft_token_contrast():
    # Dark mode used to only override --paper/--card/--ink/--line — the "-soft" tint tokens
    # (--accent-soft etc., meant as a pale light-mode background behind --ink text) stayed at
    # their pale light-mode values while --ink switched to near-white, making text on top of
    # them (e.g. the PO/Invoice input's .po-filled state) unreadable. This checks each -soft
    # token actually changes value under dark mode rather than staying at the light-mode default.
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("""
                async () => {
                  await db.collection('orders').doc('o1').set({ so:'A1', customer:'Cust A1', product:'X', price:1000, po:'INV001', date:'2026-09-05', shipDate:'2026-09-10', status:'done', createdBy:'admin1' });
                }
            """)
            page.wait_for_timeout(400)

            light_values = page.evaluate("""
                () => ['--accent-soft', '--sun-soft', '--danger-soft', '--info-soft'].map(
                  v => getComputedStyle(document.documentElement).getPropertyValue(v).trim()
                )
            """)
            page.evaluate("() => applyTheme('dark')")
            page.wait_for_timeout(150)
            dark_values = page.evaluate("""
                () => ['--accent-soft', '--sun-soft', '--danger-soft', '--info-soft'].map(
                  v => getComputedStyle(document.documentElement).getPropertyValue(v).trim()
                )
            """)
            for name, light, dark in zip(["--accent-soft", "--sun-soft", "--danger-soft", "--info-soft"], light_values, dark_values):
                assert light != dark, f"{name} must be overridden for dark mode, still {dark!r} (same as light mode)"

            # spot-check the PO/Invoice field specifically, since that's the reported symptom
            page.evaluate("() => showTab('orders')")
            page.wait_for_timeout(300)
            colors = page.evaluate("""
                () => {
                  const input = document.querySelector('#ordersBody .locked-input-group input');
                  const group = input.closest('.locked-input-group');
                  return { text: getComputedStyle(input).color, groupBg: getComputedStyle(group).backgroundColor };
                }
            """)
            assert colors["groupBg"] != "rgb(229, 240, 254)", (
                f"PO/Invoice field background is still the light-mode pale blue in dark mode: {colors}"
            )

            # The native <input type=date> calendar icon is drawn in a fixed dark color by the
            # browser itself (no currentColor support) — invisible on a dark card unless inverted.
            # getComputedStyle(el, '::-webkit-calendar-picker-indicator') isn't reliably queryable
            # in Chromium for this UA pseudo-element (confirmed empirically: reads back 'none' even
            # though the rule visibly takes effect on screen), so check the stylesheet rule itself
            # exists instead of trying to read the pseudo-element's resolved style.
            has_dark_invert_rule = page.evaluate("""
                () => Array.from(document.styleSheets).some(sheet => {
                  try {
                    return Array.from(sheet.cssRules).some(rule =>
                      rule.selectorText &&
                      rule.selectorText.includes('calendar-picker-indicator') &&
                      rule.selectorText.includes('dark') &&
                      rule.style.filter && rule.style.filter.includes('invert')
                    );
                  } catch (e) { return false; }
                })
            """)
            assert has_dark_invert_rule, "no dark-mode invert() rule found for the date input's calendar icon"

            assert errors == [], f"JS error(s) during dark mode contrast check: {errors}"
    print("check_dark_mode_soft_token_contrast: OK")


def check_warranty_alert_dismiss():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("""
                async () => {
                  // shipDate chosen so warranty (12 mo) expires `daysAhead` days from today -> "soon" (<=30 days)
                  const ship = (daysAhead) => { const d = new Date(); d.setHours(12,0,0,0); d.setMonth(d.getMonth()-12); d.setDate(d.getDate()+daysAhead); return d.toISOString().slice(0,10); };
                  await db.collection('orders').doc('o1').set({
                    so:'A1', customer:'Cust A1', product:'X', price:1000,
                    date:ship(5), shipDate:ship(10), po:'INV001',
                    warrantyMonths: 12, status:'done', createdBy:'admin1'
                  });
                }
            """)
            page.wait_for_timeout(500)
            page.evaluate("() => showTab('dashboard')")
            page.wait_for_timeout(300)

            has_dismiss_btn = page.evaluate(
                "() => !!document.getElementById('dashboardAlert').querySelector('.alert-dismiss-btn')"
            )
            assert has_dismiss_btn, "warranty-soon banner should show a dismiss button"

            page.click("#dashboardAlert .alert-dismiss-btn")
            page.wait_for_timeout(100)
            after_dismiss = page.evaluate("() => document.getElementById('dashboardAlert').style.display")
            assert after_dismiss == "none", "clicking dismiss should hide the banner"

            # re-rendering with the exact same underlying alert must stay dismissed (localStorage-backed)
            page.evaluate("() => renderDashboard()")
            page.wait_for_timeout(100)
            after_rerender = page.evaluate("() => document.getElementById('dashboardAlert').style.display")
            assert after_rerender == "none", "dismissal should survive a re-render of the same alert"

            # a genuinely NEW warranty-soon order must bring the banner back (different signature)
            page.evaluate("""
                async () => {
                  // shipDate chosen so warranty (12 mo) expires `daysAhead` days from today -> "soon" (<=30 days)
                  const ship = (daysAhead) => { const d = new Date(); d.setHours(12,0,0,0); d.setMonth(d.getMonth()-12); d.setDate(d.getDate()+daysAhead); return d.toISOString().slice(0,10); };
                  await db.collection('orders').doc('o2').set({
                    so:'A2', customer:'Cust A2', product:'Y', price:500,
                    date:ship(15), shipDate:ship(20), po:'INV002',
                    warrantyMonths: 12, status:'done', createdBy:'admin1'
                  });
                }
            """)
            page.wait_for_timeout(400)
            after_new_alert = page.evaluate("() => document.getElementById('dashboardAlert').style.display")
            assert after_new_alert == "flex", "a new order entering warranty-soon status should reopen the banner"

            assert errors == [], f"JS error(s) during warranty alert dismiss check: {errors}"
    print("check_warranty_alert_dismiss: OK")


SEED_PROMO_ORDERS = """
async () => {
  const col = db.collection('orders');
  await col.doc('p1').set({ so:'S1', customer:'Alpha Co', product:'Widget', price:100, date:'2026-03-01', shipDate:'2026-03-10', status:'done', po:'INV-111', createdBy:'admin1' });
  await col.doc('p2').set({ so:'S2', customer:'Beta Ltd', product:'Gadget', price:200, date:'2026-03-02', shipDate:'2026-03-15', status:'done', po:'INV-222', createdBy:'admin1' });
  await col.doc('p3').set({ so:'S3', customer:'Gamma Inc', product:'Gizmo', price:300, date:'2026-03-03', shipDate:'2026-03-20', status:'done', po:'', createdBy:'admin1' });
  await col.doc('p4').set({ so:'S4', customer:'Delta', product:'Thing', price:400, date:'2026-04-01', shipDate:'2026-04-05', status:'done', po:'INV-444', createdBy:'admin1' });
  await db.collection('promotions').doc('promoMar').set({ name:'Promo March', month:2, year:2026, giftLabel:'Mug', createdBy:'admin1' });
  await db.collection('promotions').doc('promoApr').set({ name:'Promo April', month:3, year:2026, giftLabel:'Cap', createdBy:'admin1' });
}
"""

PROMO_ROWS_JS = """
() => [...document.querySelectorAll('#promoOrdersBody tr')].map(tr =>
  [...tr.querySelectorAll('td')].map(td => td.textContent.trim()))
"""


def _promo_search(page, text):
    page.fill("#promoOrdersSearch", text)
    page.wait_for_timeout(100)
    return page.evaluate(PROMO_ROWS_JS)


def check_promo_modal_invoice_column_and_search():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_PROMO_ORDERS)
            page.wait_for_timeout(400)
            page.evaluate("() => showTab('promotions')")
            page.wait_for_timeout(200)
            page.evaluate("() => openPromoModal('promoMar')")
            page.wait_for_timeout(200)

            headers = page.evaluate(
                "() => [...document.querySelectorAll('#promoModal thead th')].map(th => th.textContent.trim())"
            )
            assert headers[:2] == ["ลูกค้า", "เลขที่ Invoice"], f"invoice column should follow ลูกค้า, got {headers}"

            rows = page.evaluate(PROMO_ROWS_JS)
            assert len(rows) == 3, f"March promo should list 3 qualifying orders, got {rows}"
            by_customer = {r[0]: r for r in rows}
            assert by_customer["Alpha Co"][1] == "INV-111", f"invoice cell should show o.po, got {by_customer['Alpha Co']}"
            assert by_customer["Gamma Inc"][1] == "-", f"empty po should render '-', got {by_customer['Gamma Inc']}"

            # search by po
            rows = _promo_search(page, "inv-222")
            assert [r[0] for r in rows] == ["Beta Ltd"], f"search by po should match Beta Ltd only, got {rows}"
            # search by customer
            rows = _promo_search(page, "gamma")
            assert [r[0] for r in rows] == ["Gamma Inc"], f"search by customer should match Gamma Inc only, got {rows}"
            # no match -> single colspan-5 empty row
            rows = _promo_search(page, "zzz-nothing")
            empty = page.evaluate(
                "() => { const td = document.querySelector('#promoOrdersBody td.empty-row'); return td ? [td.colSpan, td.textContent.trim()] : null; }"
            )
            assert len(rows) == 1 and empty == [5, "ไม่พบข้อมูลที่ค้นหา"], f"no-match empty row wrong: {rows} / {empty}"

            # ticking a checkbox while filtered writes the right promotionPrepared doc
            _promo_search(page, "beta")
            page.check("#promoOrdersBody input[type=checkbox]")
            page.wait_for_timeout(300)
            prepared = page.evaluate(
                "() => (data.promotionPrepared||[]).filter(x => x.prepared).map(x => x.id)"
            )
            assert prepared == ["promoMar_p2"], f"filtered checkbox should write promoMar_p2, got {prepared}"
            still_filtered = page.evaluate(PROMO_ROWS_JS)
            assert [r[0] for r in still_filtered] == ["Beta Ltd"], "snapshot re-render must keep the search filter"

            # opening a different promotion clears the search box and shows its own orders unfiltered
            page.fill("#promoOrdersSearch", "alpha")
            page.evaluate("() => openPromoModal('promoApr')")
            page.wait_for_timeout(100)
            assert page.input_value("#promoOrdersSearch") == "", "search should clear when opening a different promotion"
            rows = page.evaluate(PROMO_ROWS_JS)
            assert [r[0] for r in rows] == ["Delta"], f"April promo should show its own unfiltered order, got {rows}"

            assert errors == [], f"JS error(s) during promo modal check: {errors}"
    print("check_promo_modal_invoice_column_and_search: OK")


def check_promo_modal_english():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_PROMO_ORDERS)
            page.wait_for_timeout(400)
            page.evaluate("() => showTab('promotions')")
            page.wait_for_timeout(200)
            page.evaluate("() => document.getElementById('langToggleBtn').click()")  # lives in the hidden rail menu popover
            page.wait_for_timeout(200)
            page.evaluate("() => openPromoModal('promoMar')")
            page.wait_for_timeout(200)

            headers = page.evaluate(
                "() => [...document.querySelectorAll('#promoModal thead th')].map(th => th.textContent.trim())"
            )
            assert headers[1] == "Invoice No.", f"invoice header not translated: {headers}"
            ph = page.get_attribute("#promoOrdersSearch", "placeholder")
            assert ph == "Search customer / invoice no. / product", f"search placeholder not translated: {ph!r}"
            _promo_search(page, "zzz-nothing")
            empty = page.evaluate("() => document.querySelector('#promoOrdersBody td.empty-row').textContent.trim()")
            assert empty == "No matching results", f"empty-state not translated: {empty!r}"

            assert errors == [], f"JS error(s) during promo English check: {errors}"
    print("check_promo_modal_english: OK")


STUB_XLSX_WRITE = """
() => {
  window.__xlsxCalls = [];
  XLSX.writeFile = (wb, filename) => {
    const name = wb.SheetNames[0];
    window.__xlsxCalls.push({ filename, sheet: name, rows: XLSX.utils.sheet_to_json(wb.Sheets[name]) });
  };
}
"""


def check_promo_report_download():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate(SEED_PROMO_ORDERS)
            page.evaluate("() => db.collection('promotions').doc('promoEmpty').set({ name:'Promo/Empty', month:0, year:2020, giftLabel:'Pen', createdBy:'admin1' })")
            page.evaluate("() => db.collection('promotionPrepared').doc('promoMar_p2').set({ prepared: true })")
            page.wait_for_timeout(400)
            page.evaluate("() => showTab('promotions')")
            page.wait_for_timeout(200)
            page.evaluate(STUB_XLSX_WRITE)
            page.evaluate("() => openPromoModal('promoMar')")
            page.wait_for_timeout(200)
            assert page.is_visible("#promoReportBtn"), "report button should be visible in the promo modal"
            # search box must not narrow the export
            _promo_search(page, "alpha")
            page.click("#promoReportBtn")
            page.wait_for_timeout(100)
            calls = page.evaluate("() => window.__xlsxCalls")
            assert len(calls) == 1, f"expected one XLSX.writeFile call, got {calls}"
            c = calls[0]
            assert c["filename"].startswith("promotion-Promo-March-") and c["filename"].endswith(".xlsx"), f"bad filename {c['filename']}"
            assert len(c["sheet"]) <= 31, f"sheet name too long: {c['sheet']}"
            rows = c["rows"]
            assert len(rows) == 4, f"3 orders + 1 total row expected, got {rows}"
            expected_cols = ["ลำดับ", "SO", "ลูกค้า", "เลขที่ Invoice", "สินค้า", "ยอดเงิน", "วันที่สั่งซื้อ",
                             "วันที่ส่งสินค้า", "สินค้าโปรโมชั่น", "สถานะการเตรียม", "สร้างโดย"]
            assert list(rows[0].keys()) == expected_cols, f"columns wrong: {list(rows[0].keys())}"
            assert [r["ลูกค้า"] for r in rows[:3]] == ["Alpha Co", "Beta Ltd", "Gamma Inc"], f"order/sort wrong: {rows}"
            assert rows[1]["สถานะการเตรียม"] == "เตรียมแล้ว" and rows[0]["สถานะการเตรียม"] == "ยังไม่เตรียม", f"prepared status wrong: {rows}"
            assert rows[0]["ยอดเงิน"] == 100, f"amount should be a number: {rows[0]}"
            assert rows[3]["ยอดเงิน"] == 600 and "1/3" in rows[3]["สถานะการเตรียม"], f"total row wrong: {rows[3]}"
            # a promotion with no qualifying orders toasts instead of downloading
            page.evaluate("() => openPromoModal('promoEmpty')")
            page.wait_for_timeout(100)
            page.click("#promoReportBtn")
            page.wait_for_timeout(100)
            assert page.evaluate("() => window.__xlsxCalls.length") == 1, "empty promotion must not download a file"
            assert errors == [], f"JS error(s) during promo report check: {errors}"
    print("check_promo_report_download: OK")


CHECKS = [
    check_order_date_and_price_inline_edit,
    check_orders_animation_plays_once,
    check_sign_out_hides_person_filter,
    check_trash_purge_banner_and_bulk_delete,
    check_commission_config_anchor_guard,
    check_gp_target_is_a_locked_constant,
    check_dark_mode_soft_token_contrast,
    check_warranty_alert_dismiss,
    check_promo_modal_invoice_column_and_search,
    check_promo_modal_english,
    check_promo_report_download,
]


def main():
    failed = []
    for check in CHECKS:
        try:
            check()
        except AssertionError as e:
            failed.append((check.__name__, str(e)))
            print(f"{check.__name__}: FAILED — {e}", file=sys.stderr)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
