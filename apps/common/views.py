from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "error": {
                "code": "csrf_failed",
                "message": "Refresh the page and try again.",
                "fields": {},
            },
            "request_id": getattr(request, "request_id", None),
        },
        status=403,
    )
