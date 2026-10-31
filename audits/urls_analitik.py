from django.urls import path

from . import views_analitik

app_name = "analitik"

urlpatterns = [
    path("", views_analitik.beranda, name="beranda"),
    path("tren/<int:unit_pk>/", views_analitik.tren, name="tren"),
]
