from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("<int:pk>/dokumen/", views.daftar, name="daftar"),
    path("<int:pk>/dokumen/<int:dokumen_pk>/unduh/<str:bentuk>/", views.unduh, name="unduh"),
    path("<int:pk>/dokumen/<int:dokumen_pk>/buat-ulang/", views.buat_ulang, name="buat_ulang"),
    path("<int:pk>/dokumen/<int:dokumen_pk>/scan/", views.unggah_scan, name="unggah_scan"),
    path("<int:pk>/nomor-surat/terbitkan/", views.terbitkan_nomor, name="terbitkan_nomor"),
    path("<int:pk>/nomor-surat/<int:nomor_pk>/koreksi/", views.koreksi_nomor, name="koreksi_nomor"),
]
