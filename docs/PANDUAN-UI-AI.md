# Panduan UI AMITRA (brief desain)

Dokumen ini adalah **rujukan desain**: konteks produk, aturan, sistem desain, inventaris halaman, dan cara
memasukkan hasil rancangan ke aplikasi. **Prompt siap tempel ada di berkas terpisah:
[PROMPT-UI-AI.md](PROMPT-UI-AI.md).**

Hasil AI dipakai sebagai **rancangan tampilan**. Logika, data, dan hak akses tetap dari aplikasi Django.

---

## 1. Alur kerja

1. Buka [PROMPT-UI-AI.md](PROMPT-UI-AI.md), tempel **Prompt Induk** ke alat AI (v0, Lovable, Bolt, dsb.)
   dan lampirkan logo `static/img/logo-scu.svg` serta `static/img/logo-scu-teks.png`.
2. Kirim prompt halaman satu per satu, dimulai dari **P0 Sistem desain dan kerangka**.
3. Buka hasil HTML di browser untuk melihat tampilannya. Periksa dengan **Checklist** (bagian 9).
4. Simpan tiap hasil di `docs/ui-rancangan/<halaman>.html`, lalu minta integrasi per halaman (bagian 10).

---

## 2. Konteks produk

**AMITRA** adalah Sistem Informasi Audit Mutu Internal untuk Lembaga Penjaminan Mutu (LPM)
Soegijapranata Catholic University (SCU). Satu siklus AMI:

```
LPM membuka periode & plot tim
  → Auditee mengisi SER per butir: kategori evaluasi diri (1–4) + penjelasan + bukti, lalu mengirim
  → 3/5/7 auditor melihat pilihan auditee, mencocokkannya dengan bukti, lalu menilai sendiri dan mengunci
  → Sistem menghitung nilai (N, D, NE) dari penilaian auditor; bila deviasi tinggi → Audit Lapangan
  → Ketua merumuskan temuan dan kesimpulan
  → Auditee menyetujui (atau keberatan sekali)
  → Final: dokumen PDF + email; auditee mengisi rencana PTK
  → Periode berikutnya: auditor memverifikasi PTK
```

### Pengguna

| Peran | Siapa | Yang paling sering dilakukan | Perangkat |
|---|---|---|---|
| Master Admin | Kepala LPM | Memantau semua audit, plot tim, buka kunci, pengaturan | Laptop |
| Admin | Staf LPM | Dashboard monitoring, plot audit, standar | Laptop |
| Auditee | Kaprodi/Dekan/Kepala biro | Mengisi SER, menyetujui hasil, mengisi PTK | Laptop & **ponsel** |
| Auditor | Dosen bersertifikat | Menilai butir sambil membaca SER dan bukti | **Laptop 13 inci** |
| Ketua auditor | Salah satu auditor | Rekonsiliasi, Audit Lapangan, merumuskan temuan | Laptop |
| Viewer | Rektorat | Grafik, tren, rapor | Laptop & tablet |

Banyak pengguna memakai sistem setahun sekali dan sebagian berusia lanjut: tampilan tenang, jelas, tidak
padat, dan **satu tombol aksi utama per langkah**.

### Prinsip UX dari BRD (wajib)

- **NFR-18** Beranda tiap peran = **Tugas Saya**: daftar tugas, tenggat, satu tombol aksi utama.
- **NFR-19** Semua teks **Bahasa Indonesia** dengan istilah LPM (bagian 5).
- **NFR-20** **Stepper progres** posisi audit dan langkah berikutnya (*belum ada, perlu dirancang*).
- **NFR-21** Aksi permanen (kirim SER, kunci penilaian, setujui) lewat **ringkasan konfirmasi**, bukan `alert()`.
- **NFR-22** Responsif mulai **360 px**; tampilan berdampingan auditor nyaman di **laptop 13 inci**.
- **NFR-23** **WCAG 2.1 AA**: kontras, keyboard, label form, fokus terlihat.

### Aturan skor yang memengaruhi tampilan (BR-01, revisi 31 Okt 2026)

- Auditee **memilih kategori 1–4** per butir (KTS, OB, Sesuai, Pelampauan), sama dengan skala auditor. Wajib
  diisi bersama penjelasan dan minimal satu bukti sebelum SER bisa dikirim.
- Setiap auditor **melihat pilihan auditee sejak mulai menilai**, mencocokkannya dengan bukti, lalu memilih
  kategorinya sendiri.
- Kategori auditee **hanya pembanding**: tidak masuk N, D, NE, NK, KKM, dan tidak menentukan butir "berbeda".
- Tampil di: halaman SER, halaman penilaian auditor, tabel perbedaan, Daftar Tilik (PDF/Excel).
- Angka skor (1–4) berasal dari Pengaturan periode; di UI cukup tampilkan **nama kategori dan artinya**.

---

## 3. Batasan teknis (jangan dilanggar)

- **Template Django + Tailwind CSS v4 + HTMX + Alpine.js.** Tidak ada React/Vue/Angular.
- Hasil AI berupa **HTML biasa dengan kelas Tailwind v4**. Interaksi kecil: **Alpine.js**. Pembaruan sebagian
  halaman: **HTMX**.
- **Tanpa pustaka JS baru** (Chart.js, recharts, jQuery, lucide-react, ikon font). Ikon: **SVG inline** (boleh
  menyalin bentuk ikon Lucide sebagai SVG).
- **Grafik** dibuat server sebagai **SVG**; AI cukup merancang wadah, legenda, dan tabel data.
- **Tanpa font CDN**; pakai *system font stack*.
- Form tetap `<form method="post">` dengan `<label for>`.
- Dokumen PDF (Laporan AMI, PTK, dll.) di luar cakupan.

---

## 4. Sistem desain

### Identitas SCU (dari logo resmi di `docs/referensi`)

| Token | Warna | Kontras di putih | Dipakai untuk |
|---|---|---|---|
| `scu-ungu` | `#4D1359` | ±13:1 | Warna utama: tombol utama, tautan, menu aktif, judul |
| `scu-ungu-gelap` | `#3A0E43` | | Hover tombol utama |
| `scu-ungu-muda` | `#F5EDF7` | | Latar menu aktif, latar sorotan ringan |
| `scu-kuning` | `#F1B800` | ±1,9:1 | **Aksen saja**: garis penanda menu aktif, titik dekorasi. **Jangan untuk teks di latar putih** |

Logo: `static/img/logo-scu.svg` (huruf "S", 1,8 KB) untuk header/sidebar, `static/img/logo-scu-teks.png`
(S + "Soegijapranata Catholic University") untuk halaman masuk.

### Warna fungsi

| Fungsi | Kelas Tailwind | Catatan |
|---|---|---|
| Netral | `slate-50` latar, `slate-200` garis, `slate-600/700/900` teks | |
| Sukses | `green-50/200/700/800` | Tersimpan, Memenuhi KKM, Efektif |
| Peringatan | `amber-50/200/300/800/900` | Tenggat dekat, deviasi tinggi. Bedakan dari kuning SCU dengan ikon + teks |
| Bahaya | `red-50/200/700/800` | Galat, Belum Memenuhi KKM, hapus |
| Info | `sky-50/200/900` | Himbauan, petunjuk |

**Kategori** (selalu dengan teks): KTS = merah, OB = amber, Sesuai = hijau, Pelampauan = biru.

### Komponen yang sudah ada di `assets/css/app.css`

`tombol`, `tombol-utama`, `tombol-kedua`, `kartu`, `isian`, `label`. Boleh didesain ulang (mis. tombol utama
menjadi ungu SCU); namanya dipertahankan agar template lama ikut berubah.

### Pola yang sudah ada di v2

Banner tenggat, pesan sistem, indikator autosave + kotak konflik antar-tab, daftar butir dengan titik
status, status dokumen yang diperbarui otomatis.

---

## 5. Glosarium (pakai persis)

| Istilah | Arti |
|---|---|
| **AMI** | Audit Mutu Internal |
| **SER** | *Self Evaluation Report*: isian auditee per butir (kategori evaluasi diri, penjelasan, bukti) |
| **Butir / Pernyataan standar** | Satu baris standar yang diisi auditee dan dinilai auditor (mis. "1.3") |
| **Kategori evaluasi diri** | Kategori 1–4 pilihan auditee; pembanding bagi auditor, tidak dihitung |
| **Bukti** | Tautan Google Drive (disarankan) atau berkas (PDF/Office/JPG/PNG, maks. 20 MB) |
| **Kategori** | **KTS** Ketidaksesuaian · **OB** Observasi · **Sesuai** · **Pelampauan** |
| **Arti kategori** | KTS: dokumen tidak tersedia dan belum terimplementasi · OB: dokumen belum lengkap, tetapi sudah terimplementasi · Sesuai: dokumen lengkap dan terimplementasi dengan baik · Pelampauan: dokumen dan implementasi melampaui standar |
| **Dasar penilaian / Kondisi faktual** | Alasan auditor; kondisi faktual wajib untuk KTS/OB |
| **Kunci penilaian** | Auditor menyelesaikan penilaiannya; setelah itu tidak bisa diubah |
| **N / D / NE** | Nilai per auditor (skala 100) / Deviasi (N tertinggi − terendah) / Nilai Efektif |
| **KKM** | Batas lulus 75: "Memenuhi KKM" / "Belum Memenuhi KKM" |
| **Audit Lapangan** | Kunjungan bila D > 10 dan NE ≥ 75 |
| **Rekonsiliasi** | Ketua menetapkan kategori butir yang seri |
| **Temuan** | Kelebihan, KTS/OB, Peluang Peningkatan |
| **Kesimpulan A/B/C**, **NK** | A dokumentasi, B implementasi SPMI, C tindak lanjut PTK lalu; NK = Nilai Kesimpulan |
| **PTK** | Permintaan Tindakan Koreksi (satu per temuan KTS/OB), mis. "PTK No. 001" |
| **CP LPM** | Kontak person LPM untuk Audit Lapangan |

### Status audit dan warna badge

| Status | Siapa bertindak | Warna |
|---|---|---|
| Belum Mulai | Auditee | slate |
| Pengisian SER | Auditee | sky |
| Penilaian Auditor | Auditor | indigo |
| Rekonsiliasi | Ketua | violet |
| Perlu Audit Lapangan | Ketua, CP LPM | amber |
| Perumusan Temuan | Ketua | cyan |
| Menunggu Persetujuan Auditee | Auditee | orange |
| Final | — | green |
| Tindak Lanjut PTK | Auditee, auditor periode berikutnya | teal |
| Ditutup | — | slate gelap |

**Stepper (NFR-20)**, 6 langkah: **Persiapan** (Belum Mulai) → **SER** (Pengisian SER) → **Penilaian**
(Penilaian Auditor, Rekonsiliasi, Perlu Audit Lapangan) → **Perumusan** → **Persetujuan** → **Selesai**
(Final, Tindak Lanjut PTK, Ditutup).

---

## 6. Referensi dari SI-AMI v1 (`C:\laragon\www\ami-scu`)

v1 dibuat dengan React + Laravel. Polanya dikenal pengguna lama, tetapi aturan dan aksesibilitasnya tidak
sesuai v2.

### Pola yang dipakai lagi

1. **Sidebar kiri** di desktop berisi logo, nama aplikasi, menu berikon, dan tombol keluar di bawah; di ponsel
   menjadi menu geser (Alpine).
2. **Ruang kerja butir**: panel kiri berisi pohon standar yang bisa dilipat, penghitung per standar ("3/5"),
   titik status per butir, butir aktif disorot; panel kanan berisi butir aktif.
3. **Pilihan kategori berupa 4 kartu besar**, kini dengan arti kategori dan radio asli (bisa keyboard).
4. **Area unggah bergaris putus-putus** untuk bukti berkas, di bawah form tautan Google Drive.
5. **Kartu statistik dengan ikon** di dashboard.
6. **Banner peringatan** untuk audit dengan deviasi tinggi.
7. **Kartu dokumen per jenis** berisi nomor surat, unduh, dan scan bertanda tangan.
8. **Jejak lokasi** di atas butir: "SER › 1 Standar Kompetensi Lulusan › 1.3".
9. Tombol bawah **"← Butir sebelumnya" / "Simpan & lanjut →"**.

### Yang tidak dipakai lagi

- Skala 0–3 dan label Peluang Perbaikan/Praktek Baik (v2: KTS/OB/Sesuai/Pelampauan, 1–4).
- Teks bahasa Inggris ("Sign in", "Submit", "Supporting Evidence", "Action Required", "Logout").
- `alert()`/`window.confirm()` sebagai konfirmasi.
- `<div onClick>` untuk butir, input tanpa label, teks 9–11 px, status hanya warna.
- Sidebar tetap tanpa versi ponsel; tinggi panel tetap (`h-[calc(100vh-8rem)]`).
- Kotak cari di topbar yang tidak berfungsi; tombol "Simulasi pengisian audit" di tampilan produksi.
- Gradasi gelap dan banyak warna dekoratif (teal, purple, indigo, emerald bercampur).
- Logo lama hitam-kuning (diganti logo SCU ungu-kuning).

---

## 7. Inventaris halaman

| # | Halaman | URL | Peran | Isi utama | Aksi utama |
|---|---|---|---|---|---|
| 1 | Masuk | `/akun/login/` | Semua | Logo SCU, tombol Google; lipatan "Masuk sebagai tamu" | Masuk dengan Google |
| 2 | Menunggu peran | `/akun/menunggu/` | Pengguna baru | Pesan menunggu penetapan peran | — |
| 3 | **Tugas Saya** | `/` | Semua (Viewer → Analitik) | Kartu per audit: unit, periode, peran, status, tenggat | Satu tombol sesuai status |
| 4 | Detail audit | `/audit/<id>/` | Tim, Admin | Status, tim, jadwal, riwayat, hasil, progres, pernyataan | Tombol sesuai peran |
| 5 | **SER** | `/audit/<id>/ser/` | Auditee (isi), auditor & Admin (baca) | Daftar butir + panel butir: pernyataan, pertanyaan panduan, **kategori evaluasi diri (4 kartu)**, penjelasan (autosave), bukti, temuan periode lalu | Tinjau dan kirim SER |
| 6 | Kirim SER | `/audit/<id>/ser/kirim/` | Auditee | Ringkasan lengkap/total, butir belum lengkap (**kategori**, penjelasan, bukti) | Kirim SER sekarang |
| 7 | **Penilaian** | `/audit/<id>/penilaian/` | Auditor | Berdampingan: isian auditee (**kategori pilihan auditee**, penjelasan, bukti) / form penilaian (4 kartu, dasar, kondisi faktual); ketua: tidak berlaku | Tinjau dan kunci penilaian |
| 8 | Kunci penilaian | `/audit/<id>/penilaian/kunci/` | Auditor | Butir belum lengkap | Kunci penilaian saya |
| 9 | Tabel perbedaan | `/audit/<id>/perbedaan/` | Auditor (setelah kunci), Admin | Butir × (**auditee**, auditor 1..n, kategori final); baris berbeda disorot | — |
| 10 | Rekonsiliasi | `/audit/<id>/rekonsiliasi/` | Ketua | Butir seri + penilaian tiap auditor | Tetapkan |
| 11 | Audit Lapangan | `/audit/<id>/audit-lapangan/` | Ketua, Admin | CP LPM, hasil awal, butir penyumbang deviasi, status tim | Selesaikan dan hitung |
| 12 | **Perumusan Temuan** | `/audit/<id>/temuan/` | Ketua, anggota (usul), Admin | Kategori final, temuan A/B/C, usulan, Kesimpulan A/B/C, checklist | Teruskan kepada auditee |
| 13 | **Hasil AMI / Persetujuan** | `/audit/<id>/persetujuan/` | Auditee, tim, Admin | NE, KKM, NK, hasil akhir, temuan, kesimpulan, checklist, keberatan | Setujui hasil AMI |
| 14 | PTK | `/audit/<id>/ptk/` | Auditee, tim | Rencana → realisasi & bukti → hasil verifikasi | Kirim rencana PTK |
| 15 | Verifikasi PTK lalu | `/audit/<id>/verifikasi-ptk/` | Auditor periode baru | Ringkasan efektif/belum; form verifikasi | Simpan verifikasi |
| 16 | Dokumen | `/audit/<id>/dokumen/` | Tim, Admin | Dokumen, nomor surat, status, unduh, scan | Unduh |
| 17 | **Plot Audit** | `/audit/` | Admin | Tabel audit + filter | Plot audit baru |
| 18 | Form plot | `/audit/plot/` | Admin | Unit, lingkup, auditee, auditor (beban, konflik, ketua), panel pemeriksaan tim | Simpan audit |
| 19 | Plot massal | `/audit/plot/impor/` | Admin | Unggah Excel → pratinjau galat | Simpan |
| 20 | **Dashboard** | `/audit/dashboard/` | Admin | Kartu ringkasan, badge status, filter, tabel progres | — |
| 21 | **Analitik** | `/analitik/` | Admin, Viewer, auditee | Grafik per butir (SVG), tabel, tren, rapor | Buat rapor |
| 22 | Tren unit | `/analitik/tren/<unit>/` | Sama | Garis NE + batang temuan per periode | — |
| 23 | Unduhan saya | `/unduhan/` | Semua | Daftar ekspor + status | Unduh |
| 24 | Notifikasi | `/notifikasi/` | Semua | Daftar, belum dibaca ditonjolkan | Tandai semua dibaca |
| 25 | Riwayat AMI unit | `/audit/riwayat/` | Auditee | Audit Final per periode + tautan | — |
| 26 | Halaman galat | 403/404/500 | Semua | Pesan + tombol kembali | Kembali ke Tugas Saya |

Administrasi (`/admin/`) memakai Django Admin dan tidak didesain ulang.

### Komponen bersama

Kerangka (sidebar + topbar ponsel), stepper, banner tenggat, kartu tugas, badge status & kategori, kartu
pilihan kategori, daftar butir, indikator autosave + konflik, daftar bukti + unggah, kartu angka, tabel
responsif, halaman konfirmasi, keadaan kosong/memuat/galat, pesan sistem (`role="status"`/`"alert"`).

---

## 8. Data contoh

- Institusi: **Soegijapranata Catholic University** · Lembaga Penjaminan Mutu
- Periode aktif: **AMI 2025/2026**; batas pengisian SER **Senin, 2 November 2026**
- Unit: Teknik Elektro (S1), Teknik Sipil (S1), Magister Teknik (S2), Ilmu Hukum (S1), Fakultas Teknik, Biro Akademik
- Pengguna: Pimpinan Teknik Sipil (auditee), Dosen Auditor 1–7, Kepala LPM, Staf LPM, Rektorat
- Butir: **1.1** Prodi memiliki profil lulusan yang terdokumentasi dan ditinjau berkala · **1.2** Capaian
  pembelajaran lulusan dirumuskan sesuai KKNI · **1.3** Tracer study dilaksanakan setiap tahun dan hasilnya
  ditindaklanjuti · **2.1** RPS tersedia untuk setiap mata kuliah dan dievaluasi tiap semester · **2.2**
  Monitoring kehadiran dosen dan mahasiswa dilakukan secara berkala
- Kategori auditee butir 1.3: **Sesuai**; auditor: Sesuai, OB, KTS
- Hasil: N = 75,00 / 87,50 / 68,75 → D = 18,75; NE = 77,03 (Memenuhi KKM) → **Perlu Audit Lapangan**
- PTK: **PTK No. 001** (KTS, butir 1.3), nomor surat **001/PTK/LPM/PA/X/2026**

---

## 9. Checklist hasil AI

- [ ] Bahasa Indonesia dengan istilah glosarium; tidak ada "Submit", "Score", "Sign in", "Logout".
- [ ] Hanya HTML + Tailwind + Alpine/HTMX; tanpa React, Chart.js, jQuery, ikon font, font CDN.
- [ ] Warna utama ungu SCU; kuning hanya aksen; tidak ada teks kuning di latar putih.
- [ ] Setiap input punya `<label>`; heading berurutan; fokus keyboard terlihat; kontras ≥ 4,5:1.
- [ ] Kategori dan status selalu dengan teks, bukan warna saja.
- [ ] Baik di 360 px dan 1280–1440 px (penilaian berdampingan).
- [ ] Satu tombol aksi utama per halaman; aksi permanen lewat halaman ringkasan.
- [ ] Ada keadaan kosong, memuat, dan galat.
- [ ] Kategori auditee tidak ditampilkan seolah-olah ikut menentukan nilai.
- [ ] Tidak menambah fitur, kolom, atau aturan yang tidak ada di aplikasi.

---

## 10. Integrasi ke aplikasi

- Kelas Tailwind dipindah ke template Django yang ada; data contoh diganti variabel template.
- Komponen berulang (badge, kartu, stepper, banner, kartu kategori) dijadikan `include`.
- Token warna SCU ditambahkan ke `@theme` di `assets/css/app.css`; `tombol-utama`, `kartu`, `isian`, dst.
  diperbarui di sana, lalu CSS dibangun ulang dengan `python scripts/tailwind.py`.
- Nama field form, `{% csrf_token %}`, `x-data="SIAMI.autosave(...)"`, dan atribut `hx-*` dipertahankan.
- Tes halaman dijalankan ulang (`pytest`).
