# Panduan Alur Audit AMITRA: dari Persiapan sampai Ditutup

Panduan ini mengikuti satu audit dari awal sampai akhir, dilihat dari tiga sudut pandang:

- **Master Admin LPM** (superadmin): menyiapkan periode, unit, pengguna, dan standar; memplot audit; turun tangan bila ada kendala.
- **Auditee**: pimpinan unit yang diaudit (misalnya kaprodi); mengisi SER, menyetujui hasil, menindaklanjuti PTK.
- **Auditor**: anggota tim penilai; salah satunya **ketua auditor** yang punya tugas tambahan.

Peran auditee dan auditor **tidak melekat pada akun**. Seseorang menjadi auditee atau auditor karena diplot di audit tertentu, jadi satu dosen bisa menjadi auditee di prodinya sekaligus auditor di prodi lain.

---

## Gambaran singkat

| Langkah di stepper | Status audit | Siapa yang bertindak | Selesai bila |
|---|---|---|---|
| 1. Persiapan | Belum Mulai | Master Admin / Admin LPM | Audit diplot |
| 2. SER | Pengisian SER | Auditee | Auditee menekan **Kirim SER sekarang** |
| 3. Penilaian | Penilaian Auditor | Semua auditor | Semua auditor mengunci penilaian |
| | Rekonsiliasi | Ketua auditor | Semua butir punya kategori final (otomatis bila tidak ada butir seri) |
| | Perlu Audit Lapangan *(hanya bila dipicu)* | Ketua auditor | Ketua menekan **Selesaikan dan hitung hasil** |
| 4. Temuan | Perumusan Temuan | Ketua auditor (anggota boleh mengusulkan) | Ketua menekan **Teruskan kepada auditee** |
| 5. Persetujuan | Menunggu Persetujuan Auditee | Auditee | Auditee menyetujui (atau mengajukan keberatan satu kali) |
| 6. Selesai | Final | Auditee | Auditee mengirim rencana PTK (tanpa KTS/OB langsung Ditutup) |
| | Tindak Lanjut PTK | Auditee, lalu auditor periode berikutnya | Semua PTK diverifikasi pada periode berikutnya |
| | Ditutup | — | — |

Setiap perpindahan status memicu notifikasi in-app (ikon lonceng) dan email ke orang yang harus bertindak berikutnya. Mulai H-3 sebelum tenggat, banner kuning muncul di atas halaman sampai tugasnya selesai.

---

## Tahap 0: Persiapan (Master Admin)

Dikerjakan sekali per periode, sebelum audit dimulai. Kecuali disebut lain, semua langkah ada di menu **Administrasi** (pojok kiri bawah menu samping).

### 0.1 Aktifkan pengguna

1. Minta semua dosen/tendik yang akan terlibat **login sekali** dengan akun Google kampus. Akun baru berstatus **Menunggu Peran** dan hanya melihat halaman tunggu.
2. Buka **Administrasi → Pengguna**, centang akun-akun tersebut, lalu pilih aksi **Tetapkan peran: Pengguna (dosen/tendik)**.
   - Staf LPM diberi peran **Admin LPM** atau **Master Admin LPM**.
   - Pimpinan yang hanya memantau diberi peran **Viewer (Rektorat)**.
   - Orang yang sudah tidak aktif diberi peran **Nonaktif** (akun tidak dihapus agar jejak audit tetap ada).
3. Isi **unit homebase** dan **unit tempat menjabat** setiap auditor. Data ini dipakai sistem untuk menolak auditor yang mengaudit unitnya sendiri.

### 0.2 Siapkan unit

1. **Administrasi → Unit**: pastikan semua unit yang diaudit ada, aktif, dengan tipe unit, induk (fakultas), dan kategori surat yang benar.

### 0.3 Buat periode

1. **Administrasi → Periode → Tambah**: isi nama periode, tahun akademik (contoh `2026/2027`), dan **CP LPM** (kontak yang ditampilkan saat audit perlu Audit Lapangan).
2. Di bagian **Tahapan periode**, isi tanggal mulai dan tanggal selesai untuk setiap tahap: Pengisian SER, Review Auditor, Audit Lapangan, Finalisasi, Tindak Lanjut PTK. Tanggal selesai Pengisian SER menjadi **batas SER** auditee.
3. Di bagian **Pengaturan periode**, periksa parameter rumus: skor tiap kategori (1–4), KKM (75), ambang deviasi (10), minimal auditor (3), angka penyesuaian KTS/OB/Kelebihan, dan bobot A/B/C. Semua angka ini dipakai per periode, tidak tertulis mati di program.
4. Simpan, lalu di daftar periode centang periode itu dan pilih aksi **Aktifkan periode terpilih**. Hanya satu periode yang boleh aktif.

### 0.4 Siapkan standar

Pilih salah satu:

- **Salin dari periode lalu:** buka periode baru → tombol **Salin standar dari periode lain**. Butir hasil salinan tetap terhubung dengan butir periode lalu, sehingga PTK lama bisa diverifikasi.
- **Impor dari Excel:** **Administrasi → Standar → Impor dari Excel**, gunakan template yang disediakan.

Periksa bahwa setiap pernyataan standar punya **tipe unit** yang tepat; hanya butir yang cocok dengan tipe unit dan lingkup bidang audit yang muncul di SER.

### 0.5 Siapkan penomoran surat

1. **Administrasi → Pola nomor surat**: pastikan ada pola untuk PTK, Laporan AMI, dan Berita Acara, dan polanya tidak sama persis.
2. **Administrasi → Pengaturan dokumen**: periksa judul dan nomor formulir setiap dokumen.

### 0.6 Plot audit (Master Admin atau Admin LPM)

1. Menu **Plot Audit → Plot audit baru**.
2. Isi **Unit yang diaudit**, **Lingkup bidang**, **Auditee**, **Auditor** (jumlah ganjil, minimal sesuai Pengaturan), **Ketua auditor** (salah satu auditor), dan bila sudah ada, **Jadwal Audit Lapangan**.
3. Tekan **Simpan audit**. Sistem menolak tim yang jumlahnya genap, ketua yang bukan auditor, atau auditor yang menjabat di unit itu.
4. Untuk banyak unit sekaligus: **Plot Audit → Plot massal (Excel)**.

Begitu disimpan, auditee dan semua auditor mendapat notifikasi penugasan, dan audit berstatus **Belum Mulai**.

> **Mengganti auditee atau auditor:** di **Plot Audit**, klik **Ubah tim** pada baris audit. Ini hanya bisa selama status **Belum Mulai** atau **Pengisian SER**. Isian SER tersimpan pada audit, bukan pada orangnya, jadi auditee pengganti tinggal melanjutkan draf yang sudah ada.

---

## Tahap 1: Pengisian SER (Auditee)

1. Login, buka **Tugas Saya**. Kartu audit unit Anda menampilkan tombol **Isi SER** dan tenggatnya.
2. Untuk setiap butir pernyataan standar, isi tiga bagian:
   1. **Kategori evaluasi diri**: pilih KTS, OB, Sesuai, atau Pelampauan sesuai kondisi unit. Pilihan ini hanya pembanding bagi auditor dan **tidak dihitung** dalam nilai audit.
   2. **Hasil/penjelasan**: uraikan kondisi unit terhadap pernyataan itu. Isian tersimpan otomatis; tombol **Simpan isian saya** juga tersedia.
   3. **Bukti dokumen pendukung**: tambahkan tautan (misalnya Google Drive yang bisa dibuka auditor) atau unggah berkas.
3. Pindah butir dengan **Butir berikutnya** atau daftar butir di samping. Penanda di daftar butir menunjukkan mana yang sudah lengkap.
4. Bila ada PTK dari periode lalu untuk butir yang sama, PTK itu tampil sebagai pengingat.
5. Setelah semua butir lengkap, tekan **Tinjau dan kirim SER**. Halaman tinjauan menunjukkan butir yang masih kurang (dengan tombol **Lengkapi butir …**) dan ringkasan kategori Anda.
6. Centang pernyataan kebenaran isian, lalu tekan **Kirim SER sekarang**.

Setelah dikirim, SER **terkunci** dan status menjadi **Penilaian Auditor**. Semua auditor mendapat notifikasi "SER siap dinilai".

> Auditor sudah bisa melihat daftar pernyataan standar di halaman detail audit sejak diplot, untuk bersiap sebelum SER dikirim.

---

## Tahap 2: Penilaian (Auditor)

### 2.1 Setiap auditor menilai secara mandiri

1. Dari **Tugas Saya**, klik **Nilai SER** (atau dari halaman detail audit: **Nilai butir**).
2. Untuk setiap butir, baca isian auditee: pernyataan standar, kategori evaluasi diri auditee, penjelasan, dan buktinya.
3. Pilih kategori **Anda sendiri** (KTS, OB, Sesuai, Pelampauan). Bila berbeda dari pilihan auditee, sistem menampilkan penanda "Berbeda dari pilihan auditee" sebagai pengingat, bukan larangan.
4. Isi **dasar penilaian** dan **kondisi** yang ditemukan. Isian tersimpan otomatis.
5. **Khusus ketua auditor:** bila sebuah butir memang tidak berlaku untuk unit ini, tekan **Tandai tidak berlaku** dan isi alasannya. Butir itu dikeluarkan dari perhitungan.
6. Setelah semua butir dinilai, tekan **Tinjau dan kunci penilaian**, lalu **Kunci penilaian saya**.

Selama belum mengunci, auditor **tidak bisa melihat** penilaian auditor lain. Setelah mengunci, penilaian auditor lain dan **Tabel perbedaan** terbuka.

### 2.2 Rekonsiliasi (Ketua auditor)

Begitu auditor terakhir mengunci, status menjadi **Rekonsiliasi** dan sistem otomatis mengambil **kategori terbanyak** sebagai kategori final setiap butir.

1. Bila ada butir **seri** (tidak ada satu kategori terbanyak), ketua mendapat notifikasi. Buka halaman detail audit → **Rekonsiliasi (n butir seri)**.
2. Untuk setiap butir seri, pilih kategori final dan tulis alasannya, lalu tekan **Tetapkan**.
3. Bila tidak ada butir seri, langkah ini dilewati otomatis.

Setelah semua butir punya kategori final, sistem menghitung **hasil awal**: nilai tiap auditor, deviasi D (nilai tertinggi − terendah), dan NE. Lalu:

- Bila **D melebihi ambang deviasi dan NE memenuhi KKM**, status menjadi **Perlu Audit Lapangan** (Tahap 2.3).
- Selain itu, status langsung menjadi **Perumusan Temuan** (Tahap 3).

### 2.3 Audit Lapangan (Ketua auditor, hanya bila dipicu)

1. Buka halaman detail audit → **Audit Lapangan**. Halaman ini menampilkan jadwal, hasil awal dan alasan pemicunya, CP LPM, serta **butir penyumbang deviasi** (butir yang kategorinya berbeda antar-auditor).
2. Laksanakan kunjungan lapangan ke unit sesuai jadwal.
3. Bila hasil kunjungan mengubah penilaian, centang butir yang perlu direvisi, lalu tekan **Buka revisi penilaian**. Semua auditor merevisi butir itu saja, lalu mengunci ulang seperti Tahap 2.1.
4. Isi catatan follow-up Audit Lapangan, lalu tekan **Selesaikan dan hitung hasil**.

Sistem menghitung hasil setelah Audit Lapangan dan status menjadi **Perumusan Temuan**.

### 2.4 Verifikasi PTK periode lalu (Auditor, bila ada)

Bila unit ini punya PTK dari periode lalu, halaman detail audit menampilkan kotak **Verifikasi PTK periode lalu**. Selama status Penilaian Auditor sampai Perumusan Temuan, ketua atau anggota auditor:

1. Membuka **Verifikasi PTK periode lalu**.
2. Membaca rencana, realisasi, dan bukti dari auditee lama.
3. Memilih hasil **Efektif** atau **Tidak efektif**, menulis catatan, lalu **Simpan**.

Setelah semua PTK lama diverifikasi, audit periode lalu otomatis **Ditutup**. Hasil verifikasi ini menjadi dasar penilaian kesimpulan **C (tindak lanjut PTK periode lalu)** di Tahap 3.

---

## Tahap 3: Perumusan Temuan (Ketua auditor)

1. Buka halaman detail audit → **Perumusan Temuan**. Halaman ini punya lima bagian:
   1. **Kategori final**: daftar kategori final per butir (hanya dibaca).
   2. **Temuan**: sistem otomatis membuat temuan **A. Kelebihan** (butir Pelampauan) dan **B. KTS/OB** (wajib PTK). Tulis uraian setiap temuan sesuai kondisi faktual, lalu **Simpan uraian**. Ketua juga bisa **Tambah** temuan **C. Peluang Peningkatan**.
   3. **Usulan anggota**: anggota auditor bisa **Kirim usulan** uraian atau peluang peningkatan. Ketua memutuskan **Terima** atau **Tolak**.
   4. **Kesimpulan**: beri skor dan penjelasan untuk A, B, C serta tandai Tujuan Audit yang tercapai, lalu **Simpan kesimpulan**.
   5. **Teruskan**: centang keempat pernyataan checklist ketua, lalu tekan **Teruskan kepada auditee**.

Sistem menghitung **hasil final** (NE final, NK, dan hasil akhir), menomori PTK, menerbitkan nomor surat, lalu status menjadi **Menunggu Persetujuan Auditee**.

> **Anggota auditor** di tahap ini bisa membuka halaman yang sama untuk membaca dan mengirim usulan, tetapi tidak bisa menyimpan uraian atau meneruskan hasil.

---

## Tahap 4: Persetujuan (Auditee)

1. Auditee mendapat notifikasi "Hasil AMI … menunggu persetujuan Anda". Di **Tugas Saya**, klik **Tinjau dan setujui hasil**.
2. Baca ringkasan: NE dan KKM, NK, hasil akhir, rekap temuan (Kelebihan, KTS, OB, Peluang Peningkatan), kesimpulan, dan Tujuan Audit.
3. Pilih salah satu:
   - **Setuju:** centang ketiga pernyataan checklist, lalu **Setujui hasil AMI**. Status menjadi **Final**.
   - **Keberatan:** tulis keberatan, lalu **Kirim keberatan**. Keberatan hanya bisa diajukan **satu kali**. Audit kembali ke **Perumusan Temuan**; ketua menulis tanggapan (**Simpan tanggapan**), memperbaiki bila perlu, lalu meneruskan lagi. Setelah itu auditee hanya bisa menyetujui.

---

## Tahap 5: Final, dokumen, dan PTK

### 5.1 Saat audit Final

- Semua pihak mendapat notifikasi dan email "Hasil AMI … Final".
- Dokumen PDF/Excel dibuat di antrean: Daftar Tilik, Temuan AMI, Laporan AMI, satu PTK per temuan KTS/OB, dan Berita Acara Audit Lapangan bila Audit Lapangan dilaksanakan. (Profil Auditee sudah dibuat sejak audit diplot.) Lihat di halaman detail audit → **Dokumen**. Status dokumen berubah menjadi **Siap** sendiri.
- Ketua auditor atau Admin LPM mengunggah **scan bertanda tangan** di halaman Dokumen bila diperlukan.
- Auditee kini bisa melihat skor setiap auditor.
- Bila **tidak ada temuan KTS/OB**, audit langsung **Ditutup**.

### 5.2 Rencana PTK (Auditee)

1. Di **Tugas Saya**, klik **Isi rencana PTK**. Setiap temuan KTS/OB punya satu PTK.
2. Untuk setiap PTK isi **akar masalah**, **rencana tindakan koreksi**, **target selesai**, dan **penanggung jawab (PIC)**, lalu **Simpan rencana**.
3. Setelah semua PTK lengkap, tekan **Kirim rencana PTK**. Rencana terkunci dan status menjadi **Tindak Lanjut PTK**.

### 5.3 Realisasi PTK (Auditee)

1. Sepanjang periode berjalan, buka halaman PTK, isi **realisasi tindakan koreksi**, lalu **Simpan realisasi**.
2. Tambahkan bukti realisasi berupa tautan atau unggahan berkas.

Realisasi bisa diperbarui sampai PTK diverifikasi.

### 5.4 Penutupan

Audit ditutup dengan salah satu cara:

- **Normal:** tim auditor unit yang sama pada periode berikutnya memverifikasi semua PTK (Tahap 2.4 di audit periode berikutnya). Setelah PTK terakhir diverifikasi, audit lama otomatis **Ditutup**.
- **Pengarsipan:** Master Admin menutup sisa audit satu periode sekaligus (lihat bagian berikut).

---

## Bila ada kendala: tindakan Master Admin

| Situasi | Tindakan | Di mana |
|---|---|---|
| Auditee terlambat atau minta waktu tambahan | **Buka kunci / perpanjang SER**: isi alasan dan batas baru | Detail audit |
| Auditee harus memperbaiki SER yang sudah dikirim | **Buka kunci / perpanjang SER** saat status Penilaian Auditor. SER kembali ke Pengisian SER dan kunci semua auditor direset (draf penilaian tetap tersimpan) | Detail audit |
| Satu auditor perlu memperbaiki penilaian yang sudah dikunci | **Reset kunci** pada nama auditor, isi alasan (selama Penilaian Auditor atau Rekonsiliasi) | Detail audit → daftar tim |
| Nomor surat salah | **Koreksi**: nomor lama ditandai batal, alasan tercatat (hanya sebelum Final) | Detail audit → Dokumen |
| Dokumen gagal dibuat | **Buat ulang** pada kartu dokumen. Bila tertahan lama, pastikan worker antrean berjalan | Detail audit → Dokumen |
| Periode berakhir dan ingin menutup semua audit Final/Tindak Lanjut PTK | **Arsipkan periode**, isi alasan, lalu **Arsipkan dan tutup audit** | Dashboard |
| Melihat jejak siapa melakukan apa | **Log** (catatan audit) | Detail audit |

Semua tindakan ini wajib disertai alasan dan tercatat di riwayat audit.

### Pembagian tugas Master Admin dan Admin LPM

| Tugas | Master Admin | Admin LPM |
|---|:-:|:-:|
| Kelola periode, unit, pengguna, peran | Ya | Hanya melihat |
| Kelola standar, impor standar | Ya | Ya |
| Plot audit, ubah tim | Ya | Ya |
| Buka kunci SER, reset kunci auditor | Ya | Tidak |
| Pantau Dashboard, Analitik, unduh dokumen | Ya | Ya |

---

## Ringkasan per sudut pandang

### Master Admin

1. Aktifkan pengguna dan tetapkan peran.
2. Siapkan unit, periode (tahapan, pengaturan, CP LPM), lalu aktifkan periode.
3. Salin atau impor standar; periksa pola nomor surat.
4. Plot audit: unit, lingkup, auditee, auditor ganjil, ketua.
5. Pantau di **Dashboard**: status per audit, progres, D, dan NE.
6. Tangani kendala (buka kunci, reset kunci, koreksi nomor, buat ulang dokumen).
7. Unduh laporan di **Dokumen** dan **Unduhan Saya**; lihat tren di **Analitik**.
8. Di akhir periode, **Arsipkan periode** bila perlu.

### Auditee

1. Login, tunggu notifikasi penugasan.
2. **Isi SER**: kategori evaluasi diri, penjelasan, bukti untuk setiap butir.
3. **Tinjau dan kirim SER** sebelum batas.
4. Tunggu penilaian (dan Audit Lapangan bila dijadwalkan).
5. **Tinjau dan setujui hasil**, atau ajukan keberatan sekali.
6. Setelah Final: **Isi rencana PTK** untuk setiap KTS/OB, lalu kirim.
7. Isi **realisasi** dan bukti PTK sepanjang periode.

### Auditor (anggota)

1. Terima notifikasi penugasan; pelajari standar di halaman detail audit.
2. Setelah SER dikirim: **Nilai SER** butir demi butir secara mandiri.
3. **Kunci penilaian saya**; setelah itu lihat **Tabel perbedaan**.
4. Revisi butir bila ketua membuka revisi pasca Audit Lapangan, lalu kunci ulang.
5. Kirim **usulan** uraian temuan atau peluang peningkatan saat Perumusan Temuan.
6. Bila unit punya PTK periode lalu: **Verifikasi PTK periode lalu**.

### Ketua auditor (tambahan dari tugas anggota)

1. **Tandai tidak berlaku** butir yang tidak relevan selama penilaian.
2. **Rekonsiliasi**: tetapkan kategori final butir seri.
3. **Audit Lapangan** bila dipicu: buka revisi bila perlu, lalu **Selesaikan dan hitung hasil**.
4. **Perumusan Temuan**: uraian temuan, putuskan usulan anggota, kesimpulan A/B/C dan Tujuan Audit, checklist, **Teruskan kepada auditee**.
5. Tanggapi keberatan auditee bila ada.
6. Unggah scan dokumen bertanda tangan bila diminta LPM.

---

## Mencoba dengan data demo

Jalankan `python manage.py runserver`, buka http://127.0.0.1:8000/, lalu pilih **Masuk sebagai tamu**. Kata sandi semua akun demo: `demo-siami-2026`. Setiap audit demo sengaja berhenti di tahap yang berbeda:

| Tahap yang ingin dicoba | Akun |
|---|---|
| Persiapan, Plot Audit, Dashboard, buka kunci, reset kunci | `master@demo.local` |
| Plot Audit, Dokumen (tanpa buka kunci) | `admin@demo.local` |
| Tahap 1: Pengisian SER | `kaprodi.ts@demo.local` |
| Tahap 2.1: Penilaian (belum mengunci) | `dosen5@demo.local` |
| Tahap 2.1 dan 2.4: Penilaian sebagai ketua, verifikasi PTK lalu | `dosen4@demo.local` |
| Tahap 2.3: Audit Lapangan | `dosen3@demo.local` |
| Tahap 4: Persetujuan | `kaprodi.ih@demo.local` |
| Tahap 5.3: Realisasi PTK | `kaprodi.te.lama@demo.local` |
| Pemantauan (hanya melihat) | `rektor@demo.local` |

Untuk mengulang dari awal (menghapus semua isi database lokal):

```powershell
Remove-Item db.sqlite3
python manage.py migrate
python manage.py isi_data_demo
```
