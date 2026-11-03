from django.contrib import admin
from django.urls import include, path

from audits.views import beranda

admin.site.site_header = "AMITRA — LPM SCU"
admin.site.site_title = "AMITRA"
admin.site.index_title = "Administrasi"

urlpatterns = [
    path("", beranda, name="beranda"),
    path("akun/", include("accounts.urls")),
    path("akun/", include("allauth.urls")),
    path("audit/", include("audits.urls")),
    path("audit/", include("findings.urls")),
    path("audit/", include("documents.urls")),
    path("notifikasi/", include("notifications.urls")),
    path("analitik/", include("audits.urls_analitik")),
    path("unduhan/", include("documents.urls_ekspor")),
    path("admin/", admin.site.urls),
]
