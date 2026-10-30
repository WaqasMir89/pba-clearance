from django.urls import include, path
from drf_spectacular.views import SpectacularJSONAPIView

from apps.audit.views import AuditListView
from apps.common.views import live, ready
from apps.complaints.views import (
    ClaimDetailView,
    ClaimListView,
    ClaimSummaryView,
    FileImportView,
    ImportDetailView,
    ImportListView,
    IntakeOptionsView,
    ReceiptDownloadView,
    SubmissionDetailView,
    TemplateView,
)
from apps.identity.views import CsrfView, LoginView, LogoutView, SessionView
from apps.policy.views import CycleListView, PolicyListView
from apps.registry.views import (
    ClientDetailView,
    ClientListView,
    OrganizationDetailView,
    OrganizationListView,
)

urlpatterns = [
    path("api/v1/", include("apps.disputes.urls")),
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
    path("api/v1/complaint-intake/options/", IntakeOptionsView.as_view()),
    path("api/v1/complaint-import-template/", TemplateView.as_view()),
    path("api/v1/complaint-imports/", ImportListView.as_view()),
    path("api/v1/complaint-imports/<uuid:pk>/", ImportDetailView.as_view()),
    path("api/v1/complaint-imports/<uuid:pk>/submit/", FileImportView.as_view()),
    path("api/v1/complaint-submissions/<uuid:pk>/", SubmissionDetailView.as_view()),
    path("api/v1/complaint-submissions/<uuid:pk>/receipt/", ReceiptDownloadView.as_view()),
    path("api/v1/claims/", ClaimListView.as_view()),
    path("api/v1/claims/summary/", ClaimSummaryView.as_view()),
    path("api/v1/claims/<uuid:pk>/", ClaimDetailView.as_view()),
]
