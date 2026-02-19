import time

from django.conf import settings
from django.contrib.auth import logout
from django.utils.deprecation import MiddlewareMixin


class VaryAcceptMiddleware(MiddlewareMixin):
    """Add `Vary: Accept` header on HTML responses so caches handle WebP negotiation.

    Lightweight and safe: only modifies responses with Content-Type text/html.
    """
    def process_response(self, request, response):
        ctype = response.get('Content-Type', '')
        if ctype and 'text/html' in ctype.lower():
            vary = response.get('Vary')
            if vary:
                if 'Accept' not in [v.strip() for v in vary.split(',')]:
                    response['Vary'] = vary + ', Accept'
            else:
                response['Vary'] = 'Accept'
        return response


class IdleSessionTimeoutMiddleware(MiddlewareMixin):
    """
    Enforce idle session timeout with separate thresholds for staff and regular users.
    """

    SESSION_LAST_ACTIVITY_KEY = 'core_idle_last_activity_ts'
    SESSION_TIMEOUT_REASON_KEY = 'core_idle_timeout_reason'
    ACTIVITY_TOUCH_INTERVAL_SECONDS = 60

    def _timeout_seconds_for_user(self, user):
        if getattr(user, 'is_staff', False):
            return int(getattr(settings, 'SESSION_IDLE_TIMEOUT_STAFF_SECONDS', 30 * 60) or 0)
        return int(getattr(settings, 'SESSION_IDLE_TIMEOUT_USER_SECONDS', 2 * 60 * 60) or 0)

    def process_request(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        timeout_seconds = self._timeout_seconds_for_user(user)
        if timeout_seconds <= 0:
            return None

        now_ts = int(time.time())
        last_activity_raw = request.session.get(self.SESSION_LAST_ACTIVITY_KEY)
        try:
            last_activity_ts = int(last_activity_raw)
        except (TypeError, ValueError):
            last_activity_ts = None

        if last_activity_ts is not None and (now_ts - last_activity_ts) > timeout_seconds:
            timeout_reason = 'staff' if getattr(user, 'is_staff', False) else 'user'
            logout(request)
            request.session[self.SESSION_TIMEOUT_REASON_KEY] = timeout_reason
            request.session.modified = True
            return None

        if last_activity_ts is None or (now_ts - last_activity_ts) >= self.ACTIVITY_TOUCH_INTERVAL_SECONDS:
            request.session[self.SESSION_LAST_ACTIVITY_KEY] = now_ts

        return None
