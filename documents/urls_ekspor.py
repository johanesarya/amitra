from django.urls import path

from . import views_ekspor

app_name = "ekspor"

urlpatterns = [
    path("", views_ekspor.daftar, name="daftar"),
    path("minta/", views_ekspor.minta, name="minta"),
    path("<int:pk>/<str:bentuk>/", views_ekspor.unduh, name="unduh"),
]
