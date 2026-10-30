from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication as DRFSessionAuthentication


class SessionAuthentication(DRFSessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = SessionAuthentication
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
