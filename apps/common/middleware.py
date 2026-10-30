from uuid import UUID, uuid4

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            request.request_id = str(UUID(request.headers.get("X-Request-ID", "")))
        except (ValueError, AttributeError):
            request.request_id = str(uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = None
        if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH"}:
            try:
                # Cache a bounded body before DRF reads its stream directly.
                if len(request.body) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                    raise RequestDataTooBig()
            except RequestDataTooBig:
                response = JsonResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "The request is too large.",
                            "fields": {},
                        },
                        "request_id": getattr(request, "request_id", None),
                    },
                    status=413,
                )
        if response is None:
            response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store, private"
            patch_vary_headers(response, ["Cookie", "X-Organization-ID"])
        return response
