from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("yonetim/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("polls.urls")),
]
