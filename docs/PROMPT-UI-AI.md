# Prompt Pembuatan UI AMITRA

Berkas ini khusus untuk **membuat tampilan baru dengan bantuan AI**. Isinya prompt siap tempel. Latar
belakang dan aturan lengkap ada di [PANDUAN-UI-AI.md](PANDUAN-UI-AI.md).

## Cara pakai

1. Buka alat AI (v0, Lovable, Bolt, dsb.) dan mulai percakapan baru.
2. **Lampirkan logo**: `static/img/logo-scu.svg` (huruf S) dan `static/img/logo-scu-teks.png` (S + nama
   universitas). Bila alat tidak menerima lampiran, AI akan memakai kotak pengganti bertuliskan "Logo SCU".
3. Tempel **Prompt Induk**, tunggu balasan "Siap".
4. Tempel prompt halaman **satu per satu**, dimulai dari **P0**. Urutan yang disarankan:
   P0 → P1 → P3 → P4 → P6 → sisanya.
5. Simpan setiap hasil sebagai `docs/ui-rancangan/<nama>.html`, lalu buka di browser untuk melihat
   tampilannya. Bila ingin diubah, balas di percakapan yang sama, mis. "buat kartu kategori lebih ringkas".
6. Bila sudah cocok, minta integrasi per halaman ke aplikasi.

| Kode | Halaman | Berkas hasil |
|---|---|---|
| P0 | Sistem desain + kerangka (sidebar, topbar ponsel) | `komponen.html` |
| P1 | Stepper progres audit | `stepper.html` |
| P2 | Masuk | `masuk.html` |
| P3 | Tugas Saya | `tugas-saya.html` |
| P4 | Pengisian SER (auditee) | `ser.html` |
| P5 | Tinjau dan kirim SER | `ser-kirim.html` |
| P6 | Penilaian auditor | `penilaian.html` |
| P7 | Tabel perbedaan + Rekonsiliasi | `perbedaan.html`, `rekonsiliasi.html` |
| P8 | Audit Lapangan | `audit-lapangan.html` |
| P9 | Perumusan Temuan | `temuan.html` |
| P10 | Hasil AMI dan persetujuan | `persetujuan.html` |
| P11 | PTK + verifikasi | `ptk.html`, `verifikasi-ptk.html` |
| P12 | Plot Audit + form plot | `plot.html`, `plot-form.html` |
| P13 | Dashboard monitoring | `dashboard.html` |
| P14 | Analitik + tren | `analitik.html`, `tren.html` |
| P15 | Dokumen, Unduhan, Notifikasi, Riwayat, Galat | `dokumen.html`, dst. |

---

## Prompt Induk

```text
Kamu adalah desainer UI/UX senior sekaligus front-end developer. Bantu saya merancang tampilan baru
aplikasi web "AMITRA" (Sistem Informasi Audit Mutu Internal) milik Lembaga Penjaminan Mutu (LPM)
Soegijapranata Catholic University (SCU), Semarang.

== PRODUK ==
Satu siklus AMI:
1. LPM memplot tim audit per unit (1 auditee, 3/5/7 auditor, salah satunya ketua).
2. Auditee mengisi SER (Self Evaluation Report) per butir pernyataan standar: memilih KATEGORI EVALUASI
   DIRI (KTS / OB / Sesuai / Pelampauan), menulis hasil/penjelasan, dan melampirkan minimal satu bukti
   (tautan Google Drive atau berkas). Setelah semua butir lengkap, auditee mengirim SER dan SER terkunci.
3. Setiap auditor melihat kategori pilihan auditee, mencocokkannya dengan bukti, lalu memilih kategorinya
   SENDIRI secara independen (+ dasar penilaian; kondisi faktual wajib untuk KTS/OB), lalu mengunci.
   Kategori auditee hanya pembanding dan TIDAK ikut dihitung.
4. Sistem menghitung N (nilai per auditor), D (deviasi), NE (nilai efektif), status KKM (75). Bila D > 10
   dan NE ≥ 75 → Audit Lapangan.
5. Ketua merumuskan temuan (Kelebihan, KTS/OB, Peluang Peningkatan) dan Kesimpulan A/B/C (NK).
6. Auditee menyetujui hasil (boleh keberatan sekali) → Final: dokumen PDF + PTK (Permintaan Tindakan
   Koreksi) → periode berikutnya PTK diverifikasi.

Arti kategori:
- KTS (Ketidaksesuaian): dokumen tidak tersedia dan belum terimplementasi
- OB (Observasi): dokumen belum lengkap, tetapi sudah terimplementasi
- Sesuai: dokumen lengkap dan terimplementasi dengan baik
- Pelampauan: dokumen dan implementasi melampaui standar

Pengguna: Master Admin & Admin (staf LPM, laptop), Auditee (pimpinan unit, laptop & ponsel), Auditor/Ketua
(dosen, laptop 13 inci, butuh tampilan berdampingan), Viewer/Rektorat (grafik). Banyak yang memakai sistem
setahun sekali dan sebagian berusia lanjut: tampilan tenang, jelas, tidak padat, SATU tombol aksi utama
per langkah.

== BATASAN TEKNIS (WAJIB) ==
- Keluaran: SATU berkas HTML statis lengkap per halaman dengan kelas Tailwind CSS v4. Untuk pratinjau pakai
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script> dan definisikan warna SCU di
  <style type="text/tailwindcss">@theme { ... }</style>.
- Bukan React/Vue. Interaksi kecil dengan Alpine.js 3 (x-data, x-show, x-model, @click) dari
  https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js. Pembaruan sebagian halaman cukup ditandai
  atribut HTMX (hx-get, hx-post, hx-target, hx-trigger); tidak perlu berfungsi.
- Tanpa pustaka lain, tanpa font CDN (system font stack), ikon hanya SVG inline bergaya garis (seperti Lucide).
- Grafik dibuat server sebagai SVG: cukup wadah, contoh SVG statis sederhana, legenda, dan tabel data.
- Form tetap <form method="post"> dengan <label for> yang benar dan atribut name yang bermakna.

== IDENTITAS VISUAL SCU ==
- Warna utama ungu SCU #4D1359 (hover #3A0E43, latar muda #F5EDF7). Aksen kuning SCU #F1B800 HANYA untuk
  garis/penanda kecil (mis. garis kiri menu aktif); jangan untuk teks di latar putih.
- Netral slate (latar slate-50, garis slate-200, teks slate-600/900). Sukses green, peringatan amber (selalu
  dengan ikon + teks agar tidak tertukar dengan kuning SCU), bahaya red, info sky.
- Kategori: KTS merah, OB amber, Sesuai hijau, Pelampauan biru, selalu dengan teks.
- Status audit dan warna badge: Belum Mulai (slate), Pengisian SER (sky), Penilaian Auditor (indigo),
  Rekonsiliasi (violet), Perlu Audit Lapangan (amber), Perumusan Temuan (cyan), Menunggu Persetujuan
  Auditee (orange), Final (green), Tindak Lanjut PTK (teal), Ditutup (slate gelap).
- Gaya: kartu putih rounded-xl, border slate-200, shadow-sm; sudut lembut; banyak ruang kosong; tanpa
  gradasi gelap atau warna dekoratif berlebihan.
- Kerangka: di layar ≥1024px SIDEBAR KIRI (logo S SCU + "AMITRA" + "Lembaga Penjaminan Mutu", menu berikon:
  Tugas Saya, Dashboard, Plot Audit, Analitik, Administrasi; nama pengguna + peran dan tombol Keluar di
  bawah). Di ponsel: topbar dengan logo, lonceng notifikasi, dan tombol menu yang membuka sidebar sebagai
  laci (Alpine). Lonceng notifikasi dengan angka belum dibaca di topbar desktop juga.

== ATURAN UX & AKSESIBILITAS ==
- Semua teks Bahasa Indonesia baku dengan istilah LPM: SER, butir, pernyataan standar, kategori evaluasi
  diri, bukti, KTS, OB, Sesuai, Pelampauan, dasar penilaian, kondisi faktual, kunci penilaian, Audit
  Lapangan, temuan, PTK, Kesimpulan A/B/C, NE, NK, KKM. Jangan memakai "Submit", "Score", "Sign in", "Logout".
- WCAG 2.1 AA: kontras ≥ 4,5:1, fokus keyboard terlihat (outline ungu), landmark header/nav/main, heading
  berurutan, tautan "Lewati ke konten", pesan dengan role="status"/"alert", elemen yang bisa diklik adalah
  <a> atau <button> (bukan <div>), pilihan kategori memakai <input type="radio"> asli di dalam kartu.
- Responsif dari 360 px; tabel lebar digulir horizontal; tampilan berdampingan untuk ≥1280 px.
- Aksi permanen (kirim SER, kunci penilaian, setujui hasil) lewat halaman/panel ringkasan konfirmasi,
  bukan alert() atau confirm().
- Sertakan keadaan kosong, memuat, dan galat bila relevan.

== CARA KERJA ==
- Saya meminta satu halaman per pesan. Gunakan data contoh realistis: unit Teknik Elektro, Teknik Sipil,
  Magister Teknik, Ilmu Hukum; periode AMI 2025/2026; Pimpinan Teknik Sipil (auditee); Dosen Auditor 1–3.
- Pakai komponen yang sama di semua halaman (tombol, kartu, badge, sidebar).
- Setelah kode, tulis singkat: komponen yang dipakai, keputusan desain penting, dan asumsi.
- Jangan menambah fitur, kolom, atau aturan yang tidak saya sebutkan.

Balas "Siap" lalu tunggu permintaan halaman pertama.
```

---

## Prompt per halaman

### P0 — Sistem desain dan kerangka

```text
Buat halaman "Panduan Komponen AMITRA" dalam satu HTML, di dalam kerangka aplikasi lengkap (sidebar desktop,
topbar + laci di ponsel, lonceng notifikasi dengan angka 3, pengguna "Dosen Auditor 1 · Auditor").
Isi halaman:
1) palet: ungu SCU dan turunannya, kuning SCU (aksen), netral, sukses, peringatan, bahaya, info, beserta
   rasio kontrasnya terhadap putih;
2) tipografi: judul halaman, judul kartu, isi, keterangan kecil (minimal 14 px untuk isi);
3) tombol: utama (ungu), kedua (bergaris), bahaya, nonaktif, dengan ikon, ukuran kecil;
4) field: input, textarea, select, checkbox, pesan galat per field, teks bantuan;
5) KARTU PILIHAN KATEGORI: 4 kartu radio (KTS, OB, Sesuai, Pelampauan) masing-masing dengan arti kategori,
   keadaan terpilih (garis ungu + latar ungu muda + ikon centang), fokus keyboard, dan versi hanya-baca;
6) badge 10 status audit dan 4 kategori;
7) pesan sistem sukses/galat/info; banner tenggat amber "Pengisian SER Teknik Sipil jatuh tempo 2 hari lagi"
   dan versi hari H berwarna merah, masing-masing dengan tombol "Selesaikan sekarang";
8) kartu angka: NE 77,03 · KKM Memenuhi · D 18,75 · NK 70,00, termasuk keadaan kosong "—";
9) indikator autosave: "Tersimpan pukul 10.42", "Menyimpan…", "Ada perubahan yang belum tersimpan", dan kotak
   konflik "Butir ini sudah diubah di tab lain pukul 10.40" dengan tombol "Muat isian terbaru" / "Simpan isian saya";
10) kartu statistik berikon (gaya dashboard);
11) keadaan kosong, memuat (skeleton), galat untuk sebuah daftar;
12) tabel responsif dengan baris disorot.
Menu aktif di sidebar: latar ungu muda, teks ungu, garis kiri kuning SCU.
```

### P1 — Stepper progres audit

```text
Rancang komponen "Stepper progres audit" untuk dipasang di atas halaman detail audit, SER, penilaian,
perumusan, dan persetujuan. 6 langkah: Persiapan → SER → Penilaian → Perumusan → Persetujuan → Selesai.
Pemetaan status: Belum Mulai = Persiapan; Pengisian SER = SER; Penilaian Auditor / Rekonsiliasi / Perlu
Audit Lapangan = Penilaian; Perumusan Temuan = Perumusan; Menunggu Persetujuan Auditee = Persetujuan;
Final / Tindak Lanjut PTK / Ditutup = Selesai.
Tampilkan langkah selesai (centang), langkah aktif (dengan sub-status, mis. "Perlu Audit Lapangan"), langkah
berikutnya, dan kalimat "Langkah berikutnya: Ketua menyelesaikan Audit Lapangan."
Buat 4 contoh: SER, Penilaian (Perlu Audit Lapangan), Persetujuan, Selesai (Tindak Lanjut PTK).
Desktop horizontal, ponsel vertikal ringkas. Aksesibel: <ol>, aria-current="step".
```

### P2 — Masuk

```text
Rancang halaman Masuk AMITRA tanpa sidebar. Latar slate-50 dengan aksen ungu tipis, kartu di tengah.
Isi: logo SCU dengan teks (lampiran logo-scu-teks.png), judul "Masuk ke AMITRA", subjudul "Sistem
Informasi Audit Mutu Internal · Lembaga Penjaminan Mutu", teks "Gunakan akun Google dengan email kampus
Anda", tombol utama "Masuk dengan Google" (ikon G berwarna). Di bawahnya lipatan "Masuk sebagai tamu
(email dan password)" berisi email, password (dengan tombol tampilkan), tombol "Masuk", tautan "Lupa
password?", catatan "Hanya untuk akun tamu yang diundang LPM". Kaki: "Akses terbatas untuk sivitas
akademika yang berwenang." Sertakan keadaan galat ("Email atau password salah.") dan keadaan "Login Google
belum dikonfigurasi". Nyaman di 360 px.
```

### P3 — Tugas Saya (beranda)

```text
Rancang halaman "Tugas Saya" untuk pengguna dengan beberapa peran sekaligus:
- Banner tenggat: "Pengisian SER Teknik Sipil jatuh tempo 2 hari lagi (Senin, 2 November 2026)".
- Sapaan "Selamat datang, Pimpinan Teknik Sipil" + periode aktif AMI 2025/2026.
- Kartu tugas (unit, periode, peran di audit itu, badge status, tenggat, progres singkat, SATU tombol utama):
  1) Teknik Sipil — Auditee — Pengisian SER — "3 dari 5 butir lengkap" — "Lanjutkan isi SER"
  2) Teknik Elektro — Ketua auditor — Penilaian Auditor — "Tenggat 12 November 2026 (5 hari lagi)" — "Nilai SER"
  3) Magister Teknik — Ketua auditor — Perlu Audit Lapangan — "Audit Lapangan"
  4) Ilmu Hukum — Auditee — Menunggu Persetujuan Auditee — "Tinjau dan setujui hasil"
  5) Teknik Elektro 2024/2025 — Auditee — Final — "Isi rencana PTK"
- Urut tenggat terdekat; kartu tenggat hari ini paling menonjol.
- Tautan sekunder "Riwayat AMI unit" dan "Rapor dan tren unit Anda".
- Keadaan kosong: "Belum ada audit yang ditugaskan kepada Anda."
```

### P4 — Pengisian SER (auditee)

```text
Rancang halaman pengisian SER, tampilan utama auditee. Pakai stepper (langkah SER aktif) di atas.
- Kepala: "Self Evaluation Report (SER)", Teknik Sipil · AMI 2025/2026 · badge Pengisian SER, "Batas
  pengisian: Senin, 2 November 2026", progres "3 dari 5 butir lengkap" (bar ungu), tombol utama "Tinjau dan
  kirim SER".
- Kotak info (sky): simpan bukti di Google Drive unit, atur akses agar auditor bisa membuka, tempel tautannya;
  unggah berkas hanya bila tidak memungkinkan; isian tersimpan otomatis.
- Panel kiri (≥1024px, lengket, bisa digulir): pohon standar yang bisa dilipat ("1 Standar Kompetensi
  Lulusan 2/3", "2 Standar Proses Pembelajaran 1/2"), tiap butir: titik status (hijau lengkap / abu belum,
  dengan teks tersembunyi untuk pembaca layar), kode dan potongan pernyataan; butir aktif disorot ungu muda.
  Di ponsel menjadi pemilih butir (select atau laci) di atas panel.
- Panel kanan: jejak "SER › 1 Standar Kompetensi Lulusan › 1.3", "Butir 3 dari 5", kode 1.3 dan pernyataan
  "Tracer study dilaksanakan setiap tahun dan hasilnya ditindaklanjuti.", pertanyaan panduan
  "Tunjukkan dokumen dan bukti pelaksanaannya."
  1) "Kategori evaluasi diri (wajib)": 4 kartu radio KTS / OB / Sesuai / Pelampauan dengan artinya, 2×2 di
     desktop, 1 kolom di ponsel; terpilih: Sesuai. Keterangan kecil: "Auditor akan mencocokkan pilihan ini
     dengan bukti Anda."
  2) "Hasil/penjelasan" textarea dengan indikator autosave "Tersimpan pukul 10.42".
  3) "Bukti (minimal satu)": daftar bukti (ikon Drive/berkas, nama, ukuran, tombol Hapus), form "Tempel tautan
     Google Drive" + "Nama bukti (opsional)" + "Tambah tautan", lalu lipatan "Unggah berkas" berisi area
     bergaris putus-putus "Pilih berkas (PDF, Word, Excel, PowerPoint, JPG, PNG; maks. 20 MB)".
  4) Kotak "Temuan periode lalu pada butir ini": PTK No. 001 · KTS (AMI 2024/2025), uraian singkat, rencana
     dan realisasi, status "belum diverifikasi efektif".
- Bawah: "← Butir sebelumnya" (kedua) dan "Simpan & lanjut →" (utama).
- Tampilkan juga 2 keadaan: SER sudah dikirim (semua hanya-baca, kategori tampil sebagai badge) dan batas lewat.
```

### P5 — Tinjau dan kirim SER

```text
Rancang halaman konfirmasi "Tinjau dan kirim SER": kartu angka "Butir lengkap 3" dan "Total butir 5",
daftar butir belum lengkap dengan tautan ke butirnya dan kekurangannya ("2.1 — belum ada kategori, bukti",
"2.2 — belum ada kategori, penjelasan, bukti"), ringkasan pilihan kategori auditee (KTS 0 · OB 1 · Sesuai 3 ·
Pelampauan 1), peringatan "Setelah dikirim, SER terkunci dan tidak dapat diubah lagi. Auditor akan mulai
menilai.", tombol "Kirim SER sekarang" yang nonaktif selama masih ada butir belum lengkap.
Buat dua keadaan: belum siap dan siap.
```

### P6 — Penilaian auditor (berdampingan)

```text
Rancang halaman penilaian auditor untuk laptop 13 inci (1280–1440px), tetap bisa dipakai di tablet. Stepper di
atas (langkah Penilaian aktif).
- Kepala: "Penilaian auditor", Teknik Elektro · AMI 2025/2026 · badge Penilaian Auditor · "Ketua auditor",
  progres "3 dari 5 butir selesai", tombol "Tabel perbedaan" (kedua) dan "Tinjau dan kunci penilaian" (utama).
- Kiri: pohon butir seperti halaman SER; butir "tidak berlaku" diredupkan dengan label.
- Tengah, 2 kolom berdampingan:
  a) "Isian auditee" (hanya-baca): kode 1.3, pernyataan, pertanyaan panduan, lalu kotak menonjol
     "Kategori pilihan auditee: Sesuai" (badge hijau + arti kategori) dengan keterangan "Cocokkan dengan bukti
     di bawah, lalu tetapkan kategori Anda sendiri.", penjelasan auditee, daftar bukti (tautan Drive membuka
     tab baru, ikon tautan luar), kotak "Temuan periode lalu pada butir ini".
  b) "Penilaian Anda": 4 kartu radio kategori dengan artinya (belum ada yang dipilih), textarea "Dasar
     penilaian (wajib)", textarea "Kondisi faktual" yang labelnya berubah menjadi "(wajib untuk KTS/OB)" saat
     KTS/OB dipilih (Alpine), indikator autosave. Bila pilihan auditor berbeda dari auditee, tampilkan catatan
     netral kecil "Berbeda dari pilihan auditee (Sesuai)" — bukan peringatan.
     Khusus ketua: lipatan "Tandai butir ini tidak berlaku" dengan alasan.
- Bawah: kartu "Penilaian auditor lain" (hanya tampil setelah auditor mengunci; tampilkan keadaan terkunci
  "Terlihat setelah Anda mengunci penilaian") dan navigasi butir.
- Keadaan tambahan: penilaian sudah dikunci (hanya-baca + tanggal kunci) dan revisi pasca Audit Lapangan
  (banner amber; hanya butir tertentu yang terbuka).
```

### P7 — Tabel perbedaan dan Rekonsiliasi

```text
Rancang dua halaman:
1) "Tabel perbedaan penilaian": tabel butir × kolom "Auditee (evaluasi diri)" × 3 auditor (kategori + dasar
   singkat + kondisi faktual) × "Kategori final" (mis. "Sesuai · Mayoritas auditor"). Kolom auditee diberi
   latar abu tipis dan keterangan "pembanding, tidak dihitung". Baris yang penilaian AUDITOR-nya berbeda
   disorot amber dengan label "Berbeda"; baris tidak berlaku diredupkan. Legenda di atas. Gulir horizontal di ponsel.
2) "Rekonsiliasi: butir tanpa kategori terbanyak": penjelasan singkat; per butir seri tampil kategori auditee
   (kecil) dan 3 kartu penilaian auditor berdampingan, lalu form ketua: select kategori + "Alasan penetapan"
   + tombol "Tetapkan".
```

### P8 — Audit Lapangan

```text
Rancang halaman "Audit Lapangan" untuk ketua. Stepper: Penilaian aktif (sub-status Perlu Audit Lapangan).
Kiri: kartu "Kontak CP LPM" (nama, email, telepon), jadwal kunjungan, "Hasil awal: D = 18,75 · NE = 77,03".
Kanan: "Butir penyumbang deviasi" (checkbox per butir, kategori tiap auditor ringkas) + tombol "Buka revisi
penilaian"; "Status penilaian tim" (Dosen Auditor 1: Terkunci; Dosen Auditor 2: Sedang merevisi); form
"Selesaikan Audit Lapangan" dengan catatan follow-up wajib, tombol nonaktif selama revisi berjalan.
```

### P9 — Perumusan Temuan

```text
Rancang halaman "Perumusan Temuan" yang panjang tetapi mudah dinavigasi (daftar isi lengket di kiri atau tab:
Kategori final · Temuan · Usulan · Kesimpulan · Checklist):
- Kategori final: tabel butir × penilaian auditor ringkas × select kategori final; bila diubah muncul
  "Alasan perubahan" + "Simpan".
- Temuan: A. Kelebihan, B. KTS/OB (dengan kode PTK), C. Peluang Peningkatan. Tiap temuan: badge jenis, butir,
  textarea uraian + "Simpan uraian", lipatan "Kondisi faktual dari auditor (3)". Peluang bisa ditambah/dihapus.
- Usulan anggota auditor: daftar dengan tombol Terima/Tolak.
- Kesimpulan A/B/C: select skor (1 Kurang, 2 Cukup, 3 Baik, 4 Sangat Baik) + penjelasan; C punya checkbox
  "Tidak berlaku (unit belum memiliki PTK periode lalu)"; info "Bahan Kesimpulan C: 1 dari 2 PTK periode lalu
  efektif". Checklist Tujuan Audit a–f.
- Checklist persetujuan ketua (4 item) + daftar syarat yang belum terpenuhi + tombol "Teruskan kepada auditee".
- Tampilkan juga versi anggota auditor (hanya-baca + form usulan).
```

### P10 — Hasil AMI dan persetujuan auditee

```text
Rancang halaman "Hasil Audit Mutu Internal" untuk auditee. Stepper: Persetujuan aktif.
- Kartu angka: NE 74,95 · "Belum Memenuhi KKM" · NK 70,00 · Hasil akhir "Menunggu keputusan LPM".
- Ringkasan temuan A/B/C (PTK No. 001 untuk KTS/OB), Kesimpulan A/B/C dengan penjelasan, Tujuan Audit ✓/✗.
- Panel samping lengket "Persetujuan auditee": 3 checkbox wajib ("Saya telah membaca seluruh temuan dan
  kesimpulan audit", "Saya memahami PTK yang wajib ditindaklanjuti unit saya", "Saya menyetujui hasil Audit
  Mutu Internal ini"), tombol "Setujui hasil AMI", lipatan "Ajukan keberatan (hanya sekali)".
- Riwayat persetujuan (ketua setuju → auditee keberatan → tanggapan ketua).
- Keadaan setelah Final: panel persetujuan hilang; muncul "Nilai per auditor" dan tautan PTK/Dokumen.
```

### P11 — PTK dan verifikasi

```text
Rancang dua halaman:
1) "Permintaan Tindakan Koreksi (PTK)" untuk auditee: langkah 1 (isi rencana per PTK: akar masalah, rencana
   tindakan, target selesai, PIC + tombol "Kirim rencana PTK" di bawah) dan langkah 2 (setelah dikirim:
   rencana hanya-baca, form "Realisasi tindak lanjut" + daftar bukti). Tiap PTK: kode, jenis, butir, uraian
   temuan, nomor surat, badge status (Terbuka / Rencana diisi / Terverifikasi efektif / Belum efektif), kotak
   hasil verifikasi bila ada.
2) "Verifikasi PTK periode lalu" untuk auditor: 4 kartu angka (Total, Efektif, Belum efektif, Belum
   diverifikasi); per PTK: rencana, realisasi, bukti, radio "Efektif / Belum efektif" + catatan + "Simpan".
```

### P12 — Plot Audit (Admin)

```text
Rancang dua halaman Admin:
1) "Plot Audit": judul + periode, tombol "Plot massal (Excel)" dan "Plot audit baru"; filter (periode,
   fakultas, tipe unit, status); tabel unit (tipe, fakultas), auditee, ketua, jumlah auditor, badge status,
   aksi "Ubah tim" / "Hapus".
2) Form "Plot audit baru": kiri — unit (select), lingkup (checkbox), auditee (select), jadwal Audit Lapangan;
   tabel calon auditor dengan pencarian, kolom pilih, nama + email, homebase, beban audit, radio "Ketua"
   (aktif hanya bila dicentang), baris konflik merah "Konflik: homebase atau jabatan di unit ini", penghitung
   "Dipilih: 4 auditor (harus ganjil)". Kanan lengket — panel "Pemeriksaan tim" dengan daftar galat atau
   "Tim memenuhi semua aturan dan siap disimpan" + tombol "Simpan audit".
```

### P13 — Dashboard monitoring (Admin)

```text
Rancang "Dashboard monitoring" untuk staf LPM (data langsung):
- 4 kartu statistik berikon: Jumlah audit 6 · SER terkirim 67% (4 dari 6) · Perlu Audit Lapangan 1 ·
  Deviasi di atas ambang 1; di bawahnya chip jumlah per status.
- Banner amber bila ada deviasi tinggi: "1 audit memiliki deviasi di atas ambang" + tautan "Lihat".
- Tombol "Ekspor data mentah periode (Excel)" dan "Arsipkan periode" (Master Admin).
- Filter: periode, fakultas, tipe unit, status, checkbox "Hanya deviasi di atas ambang".
- Tabel: unit (+tipe, fakultas, auditee), badge status, SER (x/n + bar mini), progres tiap auditor
  ("Dosen Auditor 1 (ketua): terkunci", "Dosen Auditor 2: 3/5", "belum mulai"), D (amber bila di atas ambang),
  NE, tenggat. Padat namun terbaca di laptop 13 inci.
```

### P14 — Analitik dan tren

```text
Rancang halaman "Analitik mutu" untuk Rektorat (hanya audit Final):
- Filter periode, fakultas, tipe unit, unit.
- Kartu "Skor per butir standar": contoh grafik batang SVG statis (sumbu Y 0–4, garis acuan putus-putus hijau
  di 3 = Sesuai; batang merah/amber/hijau sesuai nilai), legenda, lipatan tabel data (Butir, Rata-rata, KTS,
  OB, Sesuai, Pelampauan, n).
- Dua kolom: "Tren per unit" (daftar unit + "Lihat tren") dan "Rapor dan rekap" (rapor per fakultas, per jenjang
  prodi, rekap seluruh unit Excel + PDF).
Lalu halaman "Tren Teknik Elektro": grafik garis NE per periode dengan garis KKM 75, batang bertumpuk
KTS/OB/Kelebihan, tabel periode. Warna seri grafik: ungu SCU untuk NE.
```

### P15 — Dokumen, Unduhan, Notifikasi, Riwayat, Galat

```text
Rancang lima halaman ringkas:
1) "Dokumen" audit: kartu per jenis dokumen (Profil Auditee, Daftar Tilik, Daftar Temuan, PTK No. 001,
   Berita Acara, Laporan AMI) berisi nomor surat, status (Siap / Diantre… / Gagal + pesan), tombol Unduh PDF /
   Excel, dan "Scan bertanda tangan" (unduh atau unggah PDF). Kotak peringatan untuk Admin "Dokumen belum
   diproses lebih dari 2 menit". Bagian "Nomor surat" untuk Admin dengan aksi Koreksi dan nomor batal dicoret.
2) "Unduhan saya": daftar ekspor dengan status yang diperbarui otomatis dan tombol Excel/PDF.
3) "Notifikasi": titik ungu untuk belum dibaca, judul, ringkasan, waktu, tombol "Tandai semua dibaca", paginasi.
4) "Riwayat AMI unit": tabel periode, status, NE, tautan SER · Hasil dan temuan · PTK · Dokumen.
5) Halaman galat 403 ("Anda tidak memiliki akses ke halaman ini"), 404 ("Halaman tidak ditemukan"), 500
   ("Terjadi kesalahan pada sistem") dengan logo SCU dan tombol "Kembali ke Tugas Saya".
```
