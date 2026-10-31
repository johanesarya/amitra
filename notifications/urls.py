from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.daftar, name="daftar"),
    path("<int:pk>/", views.buka, name="buka"),
    path("tandai-semua/", views.tandai_semua, name="tandai_semua"),
]
