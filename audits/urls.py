from django.urls import path

from . import dashboard, views, views_penilaian, views_ser

app_name = "audits"

urlpatterns = [
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("riwayat/", views.riwayat, name="riwayat"),
    path("arsip/<int:periode_pk>/", views.arsip_periode, name="arsip_periode"),
    path("<int:pk>/penilaian/", views_penilaian.penilaian_halaman, name="penilaian"),
    path("<int:pk>/penilaian/kunci/", views_penilaian.penilaian_kunci, name="penilaian_kunci"),
    path("<int:pk>/penilaian/<int:pernyataan_pk>/simpan/", views_penilaian.penilaian_simpan, name="penilaian_simpan"),
    path("<int:pk>/penilaian/<int:pernyataan_pk>/tidak-berlaku/", views_penilaian.tidak_berlaku, name="tidak_berlaku"),
    path("<int:pk>/perbedaan/", views_penilaian.perbedaan, name="perbedaan"),
    path("<int:pk>/rekonsiliasi/", views_penilaian.rekonsiliasi, name="rekonsiliasi"),
    path("<int:pk>/audit-lapangan/", views_penilaian.audit_lapangan, name="audit_lapangan"),
    path("<int:pk>/reset-kunci/<int:penugasan_pk>/", views_penilaian.reset_kunci, name="reset_kunci"),
    path("<int:pk>/ser/", views_ser.ser_halaman, name="ser"),
    path("<int:pk>/ser/kirim/", views_ser.ser_kirim, name="ser_kirim"),
    path("<int:pk>/ser/buka-kunci/", views_ser.ser_buka_kunci, name="ser_buka_kunci"),
    path("<int:pk>/ser/<int:pernyataan_pk>/simpan/", views_ser.ser_simpan, name="ser_simpan"),
    path("<int:pk>/ser/<int:pernyataan_pk>/tautan/", views_ser.bukti_tautan, name="bukti_tautan"),
    path("<int:pk>/ser/<int:pernyataan_pk>/unggah/", views_ser.bukti_unggah, name="bukti_unggah"),
    path("<int:pk>/bukti/<int:bukti_pk>/hapus/", views_ser.bukti_hapus, name="bukti_hapus"),
    path("<int:pk>/bukti/<int:bukti_pk>/unduh/", views_ser.bukti_unduh, name="bukti_unduh"),
    path("", views.daftar_audit, name="daftar"),
    path("plot/", views.buat_audit, name="buat"),
    path("plot/periksa/", views.periksa_tim_view, name="periksa_tim"),
    path("plot/impor/", views.impor_plot_view, name="impor"),
    path("<int:pk>/", views.detail_audit, name="detail"),
    path("<int:pk>/ubah/", views.ubah_audit, name="ubah"),
    path("<int:pk>/hapus/", views.hapus_audit, name="hapus"),
]
