import pytest

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


@pytest.mark.django_db
def test_otp_login_e2e_live_server(live_server):
    """End-to-end smoke test for OTP login using Playwright.

    This test intercepts the backend `/accounts/otp/send/` and
    `/accounts/otp/verify-login/` routes and returns successful JSON
    responses so the full UI flow can be exercised without sending SMS.
    """
    if sync_playwright is None:
        pytest.skip('playwright not installed')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Intercept OTP endpoints and return success
        def handle_route_send(route, request):
            if request.method == 'POST' and '/accounts/otp/send/' in request.url:
                route.fulfill(status=200, body='{"ok": true}', headers={'Content-Type': 'application/json'})
            else:
                route.continue_()

        def handle_route_verify(route, request):
            if request.method == 'POST' and '/accounts/otp/verify-login/' in request.url:
                route.fulfill(status=200, body='{"ok": true}', headers={'Content-Type': 'application/json'})
            else:
                route.continue_()

        page.route('**/accounts/otp/send/', handle_route_send)
        page.route('**/accounts/otp/verify-login/', handle_route_verify)

        # Open login page
        url = f"{live_server.url}/accounts/login/"
        page.goto(url)

        # Toggle OTP area and perform flow
        page.click('#toggle-otp-login')
        page.fill('input[name="otp_phone"]', '09121112222')
        page.click('[data-otp-action="send"]')

        # Wait for verify UI and enter code
        page.wait_for_selector('[data-otp-action="verify"]', timeout=3000)
        page.fill('input[name="otp_code"]', '000000')
        page.click('[data-otp-action="verify"]')

        # Wait a bit to allow the script to handle reload
        page.wait_for_timeout(800)

        browser.close()
