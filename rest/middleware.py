from django.http import JsonResponse
from urllib.parse import urlparse

class DomainCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Define allowed domains
        allowed_domains = [
            'cote.nossi.dev',
            'api-mywuf.run.goorm.io',
            'api-mywuf.run.goorm.site',
        ]

        # Get Origin or Referer, or fallback to Host
        origin = request.META.get('HTTP_ORIGIN')
        referer = request.META.get('HTTP_REFERER')
        host = request.META.get('HTTP_HOST')

        # Default domain to None, we'll extract it later
        domain = None

        # Check origin first, then referer, then host
        if origin:
            parsed_url = urlparse(origin)
            domain = parsed_url.netloc
        elif referer:
            parsed_url = urlparse(referer)
            domain = parsed_url.netloc
        elif host:
            domain = host

        # Ensure the domain is properly set
        if domain and domain not in allowed_domains:
            return JsonResponse({
                'error': 'Forbidden Approach',
                'detail': 'Requests from this domain are not allowed.'
            }, status=403)

        user_agent = request.META.get('HTTP_USER_AGENT')

        if not user_agent or 'Postman' in user_agent or 'curl' in user_agent:
            return JsonResponse({
                'error': 'Forbidden Approach',
                'detail': 'API testing tools are not allowed.'
            }, status=403)

        # Continue with the next middleware
        return self.get_response(request)