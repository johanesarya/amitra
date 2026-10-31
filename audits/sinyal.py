from django.dispatch import Signal

# Dikirim setelah audit dibuat atau timnya diubah. Argumen: audit.
tim_audit_disimpan = Signal()

# Master Admin memperpanjang batas SER tanpa perpindahan status. Argumen: audit, alasan.
batas_ser_diperpanjang = Signal()

# Master Admin mereset kunci penilaian satu auditor. Argumen: audit, penugasan, alasan.
kunci_penilaian_direset = Signal()
