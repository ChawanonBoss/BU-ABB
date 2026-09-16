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


def check_gp_target_field():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("""
                async () => {
                  await db.collection('users').doc('alice1').set({ email:'alice@a.com', name:'Alice', role:'user' });
                  await db.collection('userTargets').doc('alice1_2026').set({ orderTarget: 1000000, shippedTarget: 900000, gpTarget: 18, uid:'alice1' });
                }
            """)
            page.wait_for_timeout(400)
            page.evaluate("() => showTab('dashboard')")
            page.wait_for_timeout(150)
            page.evaluate("() => document.querySelector('[data-dashsub=\"shipped\"]').click()")
            page.wait_for_timeout(200)

            agg_html = page.evaluate("() => document.getElementById('statGPTargetWrap').innerHTML")
            assert "<input" not in agg_html, "admin viewing the 'all' aggregate must not get an editable GP target field"

            page.evaluate("""
                () => {
                  document.getElementById('targetUserFilter').value = 'alice1';
                  document.getElementById('targetUserFilter').dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(300)
            admin_value = page.evaluate(
                "() => document.getElementById('statGPTargetWrap').querySelector('input').value"
            )
            assert admin_value == "18", f"admin viewing Alice should see her saved gpTarget=18, got {admin_value!r}"

            page.evaluate("""
                () => {
                  const input = document.getElementById('statGPTargetWrap').querySelector('input');
                  input.value = '22';
                  input.dispatchEvent(new Event('change'));
                }
            """)
            page.wait_for_timeout(300)
            saved = page.evaluate("() => __mockStore.userTargets.get('alice1_' + selectedDashboardYear).gpTarget")
            assert saved == 22, f"editing the GP target input should save to userTargets, got {saved!r}"

            page.evaluate("""
                async () => {
                  currentUserEmail = 'alice@a.com'; currentUserName = 'Alice'; currentUserUid = 'alice1';
                  await onSignedIn();
                }
            """)
            page.wait_for_timeout(500)
            page.evaluate("() => showTab('dashboard')")
            page.wait_for_timeout(150)
            page.evaluate("() => document.querySelector('[data-dashsub=\"shipped\"]').click()")
            page.wait_for_timeout(200)
            alice_own = page.evaluate("""
                () => {
                  const wrap = document.getElementById('statGPTargetWrap');
                  return { hasInput: !!wrap.querySelector('input'), text: wrap.textContent };
                }
            """)
            assert not alice_own["hasInput"], "a non-admin must never get an editable GP target field, even for themselves"
            assert alice_own["text"] == "22%", f"Alice should see her own updated target read-only, got {alice_own['text']!r}"

            assert errors == [], f"JS error(s) during GP target field check: {errors}"
    print("check_gp_target_field: OK")


def check_warranty_alert_dismiss():
    with serve_repo() as base_url:
        with new_page() as (page, errors):
            sign_in_as_admin(page, base_url)
            page.evaluate("""
                async () => {
                  await db.collection('orders').doc('o1').set({
                    so:'A1', customer:'Cust A1', product:'X', price:1000,
                    date:'2025-09-25', shipDate:'2025-09-30', po:'INV001',
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
                  await db.collection('orders').doc('o2').set({
                    so:'A2', customer:'Cust A2', product:'Y', price:500,
                    date:'2025-09-20', shipDate:'2025-09-25', po:'INV002',
                    warrantyMonths: 12, status:'done', createdBy:'admin1'
                  });
                }
            """)
            page.wait_for_timeout(400)
            after_new_alert = page.evaluate("() => document.getElementById('dashboardAlert').style.display")
            assert after_new_alert == "flex", "a new order entering warranty-soon status should reopen the banner"

            assert errors == [], f"JS error(s) during warranty alert dismiss check: {errors}"
    print("check_warranty_alert_dismiss: OK")


CHECKS = [
    check_order_date_and_price_inline_edit,
    check_orders_animation_plays_once,
    check_sign_out_hides_person_filter,
    check_trash_purge_banner_and_bulk_delete,
    check_commission_config_anchor_guard,
    check_gp_target_field,
    check_warranty_alert_dismiss,
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
