from django.dispatch import Signal

# Dikirim saat semua dokumen Final suatu audit siap (FR-42). Argumen: audit.
paket_final_siap = Signal()
