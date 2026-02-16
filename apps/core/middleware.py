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
