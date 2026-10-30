from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    if isinstance(exc, Http404):
        exc = NotFound()
    response = drf_exception_handler(exc, context)
    if response is not None:
        details = response.data
        code = getattr(exc, "default_code", "request_failed")
        message = details.get("detail") if isinstance(details, dict) else None
        response.data = {
            "error": {
                "code": str(code),
                "message": str(message or "The request could not be completed."),
                "fields": {} if message else details,
            },
            "request_id": getattr(context.get("request"), "request_id", None),
        }
    return response
