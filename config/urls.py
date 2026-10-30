from django.urls import path
from drf_spectacular.views import SpectacularJSONAPIView

from apps.audit.views import AuditListView
from apps.common.views import live, ready
from apps.identity.views import CsrfView, LoginView, LogoutView, SessionView
from apps.policy.views import CycleListView, PolicyListView
from apps.registry.views import (
    ClientDetailView,
    ClientListView,
    OrganizationDetailView,
    OrganizationListView,
)

urlpatterns = [
    path("health/live/", live),
    path("health/ready/", ready),
    path("api/v1/schema/", SpectacularJSONAPIView.as_view(), name="schema"),
    path("api/v1/auth/csrf/", CsrfView.as_view()),
    path("api/v1/auth/login/", LoginView.as_view()),
    path("api/v1/auth/logout/", LogoutView.as_view()),
    path("api/v1/auth/session/", SessionView.as_view()),
    path("api/v1/registry/organizations/", OrganizationListView.as_view()),
    path("api/v1/registry/organizations/<uuid:pk>/", OrganizationDetailView.as_view()),
    path("api/v1/registry/clients/", ClientListView.as_view()),
    path("api/v1/registry/clients/<uuid:pk>/", ClientDetailView.as_view()),
    path("api/v1/audit/", AuditListView.as_view()),
    path("api/v1/policies/", PolicyListView.as_view()),
    path("api/v1/cycles/", CycleListView.as_view()),
]
