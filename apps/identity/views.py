from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.identity.selectors import session_payload
from apps.identity.serializers import LoginSerializer, SessionSerializer


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=CsrfSerializer)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class LoginThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def get_authenticate_header(self, request):
        return "Session"

    @extend_schema(request=LoginSerializer, responses=SessionSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request=request, **serializer.validated_data)
        if user is None:
            raise AuthenticationFailed("The username or password is incorrect.")
        with transaction.atomic():
            record_event(
                actor=user,
                organization_id=None,
                action="session.signed_in",
                subject=user,
                request_id=request.request_id,
            )
        login(request, user)
        return Response(session_payload(user))


class SessionView(APIView):
    @extend_schema(responses=SessionSerializer)
    def get(self, request):
        return Response(session_payload(request.user))


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        with transaction.atomic():
            record_event(
                actor=request.user,
                organization_id=None,
                action="session.signed_out",
                subject=request.user,
                request_id=request.request_id,
            )
        logout(request)
        return Response(status=204)
