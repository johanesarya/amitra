"""Salin set standar dari periode lalu ke periode baru (FR-11)."""

from django.db import transaction

from .models import PernyataanStandar, Standar


@transaction.atomic
def salin_standar(dari, ke) -> tuple[int, int]:
    """Salin standar yang disetujui beserta pernyataannya.

    Hanya ke periode yang belum punya standar, agar tidak ada duplikasi kode.
    Mengembalikan (jumlah standar, jumlah pernyataan).
    """
    if dari.pk == ke.pk:
        raise ValueError("Periode asal dan tujuan tidak boleh sama.")
    if ke.standar.exists():
        raise ValueError("Periode tujuan sudah memiliki standar. Salin hanya ke periode yang belum memiliki standar.")

    jumlah_standar = jumlah_pernyataan = 0
    sumber = (
        Standar.objects.filter(periode=dari, status=Standar.Status.DISETUJUI)
        .prefetch_related("pernyataan__tipe_unit")
    )
    for s in sumber:
        baru = Standar.objects.create(
            periode=ke,
            kode=s.kode,
            nama=s.nama,
            lingkup_id=s.lingkup_id,
            bobot=s.bobot,
            urutan=s.urutan,
            sumber=s.sumber,
            unit_pengusul_id=s.unit_pengusul_id,
            status=s.status,
        )
        jumlah_standar += 1
        for p in s.pernyataan.all():
            p_baru = PernyataanStandar.objects.create(
                standar=baru,
                kode=p.kode,
                pernyataan=p.pernyataan,
                pertanyaan_panduan=p.pertanyaan_panduan,
                urutan=p.urutan,
                aktif=p.aktif,
                asal=p,
            )
            p_baru.tipe_unit.set(p.tipe_unit.all())
            jumlah_pernyataan += 1
    return jumlah_standar, jumlah_pernyataan
