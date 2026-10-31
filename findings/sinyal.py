from django.dispatch import Signal

# Dikirim setelah rencana/realisasi PTK disimpan atau diverifikasi. Argumen: ptk.
ptk_diperbarui = Signal()

# Dikirim setelah PTK periode lalu diverifikasi tim audit periode berikutnya. Argumen: ptk, audit_baru.
ptk_diverifikasi = Signal()
