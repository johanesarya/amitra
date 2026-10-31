"""NFR-10: log audit tak terhapus di tingkat database (bukan hanya di kode).

Trigger menolak UPDATE dan DELETE pada tabel log dan segelnya, di SQLite (development)
maupun PostgreSQL (staging/produksi).
"""

from django.db import migrations

TABEL = ["accounts_logaudit", "accounts_segellog"]
PESAN = "Log audit tidak dapat diubah atau dihapus (NFR-10)."


def pasang(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as c:
        if vendor == "sqlite":
            for t in TABEL:
                for aksi in ("UPDATE", "DELETE"):
                    c.execute(
                        f"CREATE TRIGGER {t}_tolak_{aksi.lower()} BEFORE {aksi} ON {t} "
                        f"BEGIN SELECT RAISE(ABORT, '{PESAN}'); END;"
                    )
        elif vendor == "postgresql":
            c.execute(
                "CREATE OR REPLACE FUNCTION siami_tolak_ubah_log() RETURNS trigger AS $$ "
                f"BEGIN RAISE EXCEPTION '{PESAN}'; END; $$ LANGUAGE plpgsql;"
            )
            for t in TABEL:
                c.execute(
                    f"CREATE TRIGGER {t}_tolak BEFORE UPDATE OR DELETE ON {t} "
                    "FOR EACH ROW EXECUTE FUNCTION siami_tolak_ubah_log();"
                )


def lepas(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as c:
        if vendor == "sqlite":
            for t in TABEL:
                for aksi in ("update", "delete"):
                    c.execute(f"DROP TRIGGER IF EXISTS {t}_tolak_{aksi};")
        elif vendor == "postgresql":
            for t in TABEL:
                c.execute(f"DROP TRIGGER IF EXISTS {t}_tolak ON {t};")
            c.execute("DROP FUNCTION IF EXISTS siami_tolak_ubah_log();")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_log_audit")]

    operations = [migrations.RunPython(pasang, lepas)]
