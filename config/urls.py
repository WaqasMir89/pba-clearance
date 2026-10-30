from django.urls import path
from drf_spectacular.views import SpectacularJSONAPIView

from apps.common.views import live, ready

urlpatterns = [
    path("health/live/", live),
    path("health/ready/", ready),
    path("api/v1/schema/", SpectacularJSONAPIView.as_view(), name="schema"),
]
