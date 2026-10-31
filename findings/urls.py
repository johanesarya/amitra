from django.urls import path

from . import views

app_name = "findings"

urlpatterns = [
    path("<int:pk>/temuan/", views.perumusan, name="perumusan"),
    path("<int:pk>/persetujuan/", views.persetujuan, name="persetujuan"),
    path("<int:pk>/ptk/", views.ptk, name="ptk"),
    path("<int:pk>/ptk/bukti/<int:bukti_pk>/", views.ptk_bukti, name="ptk_bukti"),
    path("<int:pk>/verifikasi-ptk/", views.verifikasi, name="verifikasi"),
    path("<int:pk>/verifikasi-ptk/bukti/<int:bukti_pk>/", views.verifikasi_bukti, name="verifikasi_bukti"),
]
