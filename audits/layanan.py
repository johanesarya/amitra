"""Aturan pembentukan tim audit (FR-13, FR-14, FR-17).

`periksa_tim()` mengembalikan daftar pesan galat dengan nama orang/unit yang
bermasalah; dipakai formulir, pengecekan langsung (HTMX), dan plot massal.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count

from accounts.models import User
from accounts.peran import Peran
from masterdata.models import PernyataanStandar
from scoring.rumus import validasi_jumlah_auditor

from .models import Audit, Penugasan
from .sinyal import tim_audit_disimpan

PERAN_BISA_DIPLOT = frozenset({Peran.PENGGUNA, Peran.ADMIN, Peran.MASTER_ADMIN})


def pengguna_bisa_diplot():
    return (
        User.objects.filter(peran__in=PERAN_BISA_DIPLOT)
        .select_related("homebase")
        .prefetch_related("unit_jabatan")
        .order_by("nama", "email")
    )


def alasan_konflik(pengguna, unit):
    """FR-14 / Bab 4: auditor tidak mengaudit homebase atau unit tempat ia menjabat."""
    if pengguna.homebase_id == unit.pk:
        return "unit tersebut adalah homebase-nya"
    if any(u.pk == unit.pk for u in pengguna.unit_jabatan.all()):
        return "ia menjabat di unit tersebut"
    return None


def beban_auditor(periode):
    """FR-14: jumlah audit tiap auditor dalam periode, {id pengguna: jumlah}."""
    return dict(
        Penugasan.objects.filter(audit__periode=periode, peran=Penugasan.Peran.AUDITOR)
        .values_list("pengguna")
        .annotate(jumlah=Count("id"))
    )


def periksa_tim(*, periode, unit, lingkup, auditee, auditor, ketua, audit=None):
    galat = []

    if audit is not None and not audit.tim_bisa_diubah:
        galat.append(
            f"Tim tidak dapat diubah karena audit sudah berstatus {audit.get_status_display()}. "
            "Hubungi Master Admin untuk membuka kunci."
        )

    lain = Audit.objects.filter(periode=periode, unit=unit)
    if audit is not None:
        lain = lain.exclude(pk=audit.pk)
    if lain.exists():
        galat.append(f"{unit} sudah memiliki audit di periode {periode}.")

    lingkup = list(lingkup)
    if not lingkup:
        galat.append("Pilih minimal satu lingkup bidang.")
    elif not PernyataanStandar.objects.berlaku_untuk(unit, periode, lingkup).exists():
        galat.append(
            f"Belum ada pernyataan standar yang berlaku untuk {unit} ({unit.tipe}) pada lingkup "
            f"{', '.join(l.nama for l in lingkup)} di periode ini."
        )

    auditor = list(auditor)
    if len({a.pk for a in auditor}) != len(auditor):
        galat.append("Ada auditor yang dipilih lebih dari sekali.")
    try:
        validasi_jumlah_auditor(len(auditor), periode.parameter())
    except ValueError as e:
        galat.append(str(e))

    if ketua is None:
        galat.append("Pilih satu ketua auditor.")
    elif ketua.pk not in {a.pk for a in auditor}:
        galat.append(f"Ketua auditor {ketua} harus salah satu auditor yang dipilih.")

    if auditee is not None and auditee.pk in {a.pk for a in auditor}:
        galat.append(f"{auditee} tidak boleh menjadi auditee sekaligus auditor di audit yang sama.")

    for orang in ([auditee] if auditee else []) + auditor:
        if orang.peran not in PERAN_BISA_DIPLOT:
            galat.append(f"{orang} berperan {orang.get_peran_display()} sehingga belum dapat diplot.")

    for a in auditor:
        alasan = alasan_konflik(a, unit)
        if alasan:
            galat.append(f"{a} tidak boleh mengaudit {unit} karena {alasan}.")

    return galat


@transaction.atomic
def simpan_audit(*, periode, unit, lingkup, auditee, auditor, ketua, oleh, jadwal_audit_lapangan=None, audit=None):
    """Buat atau ubah audit beserta timnya. Melempar ValidationError bila ada galat."""
    lingkup = list(lingkup)
    auditor = list(auditor)
    galat = periksa_tim(
        periode=periode, unit=unit, lingkup=lingkup, auditee=auditee, auditor=auditor, ketua=ketua, audit=audit
    )
    if galat:
        raise ValidationError(galat)

    try:
        with transaction.atomic():
            if audit is None:
                audit = Audit.objects.create(
                    periode=periode, unit=unit, jadwal_audit_lapangan=jadwal_audit_lapangan, dibuat_oleh=oleh
                )
            else:
                audit.unit = unit
                audit.jadwal_audit_lapangan = jadwal_audit_lapangan
                audit.save()
                audit.penugasan.all().delete()
            audit.lingkup.set(lingkup)
            Penugasan.objects.bulk_create(
                [Penugasan(audit=audit, pengguna=auditee, peran=Penugasan.Peran.AUDITEE)]
                + [
                    Penugasan(audit=audit, pengguna=a, peran=Penugasan.Peran.AUDITOR, ketua=a.pk == ketua.pk)
                    for a in auditor
                ]
            )
    except IntegrityError as e:
        # Mis. dua Admin memplot unit yang sama bersamaan.
        raise ValidationError(f"{unit} sudah memiliki audit di periode {periode}, atau tim berubah bersamaan.") from e
    tim_audit_disimpan.send(sender=Audit, audit=audit)
    return audit
