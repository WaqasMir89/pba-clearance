from django.urls import path

from apps.disputes import views

urlpatterns = [
    path("dispute-options/", views.DisputeOptionsView.as_view()),
    path("dispute-windows/", views.WindowListView.as_view()),
    path("objection-drafts/", views.DraftListView.as_view()),
    path("objection-drafts/<uuid:pk>/", views.DraftDetailView.as_view()),
    path("objection-drafts/<uuid:pk>/submit/", views.SubmitDraftView.as_view()),
    path("disputes/", views.CaseListView.as_view()),
    path("disputes/<uuid:pk>/", views.CaseDetailView.as_view()),
    path("disputes/<uuid:pk>/withdraw/", views.WithdrawView.as_view()),
    path("dispute-revisions/", views.RevisionListView.as_view()),
    path("dispute-revisions/<uuid:pk>/", views.RevisionDetailView.as_view()),
    path("dispute-revisions/<uuid:pk>/receipt/", views.RevisionReceiptView.as_view()),
    path("claim-evidence/", views.EvidenceListView.as_view()),
    path("claim-evidence/<uuid:pk>/", views.EvidenceDetailView.as_view()),
    path("claims/breakdown/", views.ClaimBreakdownView.as_view()),
]
