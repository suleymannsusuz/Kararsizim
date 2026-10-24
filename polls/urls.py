from django.urls import path

from . import views

urlpatterns = [
    path("", views.feed, name="home"),
    path("anket/olustur/", views.create, name="poll_create"),
    path("anket/<int:pk>/", views.detail, name="poll_detail"),
    path("anket/<int:pk>/oy/", views.vote, name="poll_vote"),
    path("anket/<int:pk>/kapat/", views.close, name="poll_close"),
    path("anket/<int:pk>/sil/", views.delete, name="poll_delete"),
    path("u/<str:username>/", views.user_polls, name="user_polls"),
]
