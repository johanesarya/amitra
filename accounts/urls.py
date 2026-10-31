from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("menunggu/", views.menunggu, name="menunggu"),
]
