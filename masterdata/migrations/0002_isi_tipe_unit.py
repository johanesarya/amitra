from django.db import migrations

TIPE_UNIT = [
    ("FAKULTAS", "Fakultas", 1),
    ("PRODI_S1", "Prodi S1", 2),
    ("PRODI_S2", "Prodi S2", 3),
    ("PRODI_S3", "Prodi S3", 4),
    ("PRODI_PROFESI", "Prodi Profesi", 5),
    ("LEMBAGA", "Lembaga", 6),
    ("BIRO", "Biro", 7),
    ("UPT", "UPT", 8),
]


def isi(apps, schema_editor):
    TipeUnit = apps.get_model("masterdata", "TipeUnit")
    for kode, nama, urutan in TIPE_UNIT:
        TipeUnit.objects.update_or_create(kode=kode, defaults={"nama": nama, "urutan": urutan})


def hapus(apps, schema_editor):
    apps.get_model("masterdata", "TipeUnit").objects.filter(kode__in=[t[0] for t in TIPE_UNIT]).delete()


class Migration(migrations.Migration):
    dependencies = [("masterdata", "0001_initial")]

    operations = [migrations.RunPython(isi, hapus)]
