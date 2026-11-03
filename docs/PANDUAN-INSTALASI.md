# Panduan Instalasi AMITRA di Server Linux dan Windows

Panduan ini untuk tim server (BMSI) yang memasang **AMITRA**, Sistem Informasi Audit Mutu Internal milik LPM Soegijapranata Catholic University, di server produksi.

**AMITRA dibuat dengan Python (Django), bukan PHP.** Aplikasi ini tidak berjalan di hosting PHP/cPanel biasa. Server harus bisa menjalankan Python sebagai layanan yang terus hidup, di belakang web server yang menangani HTTPS.

Di seluruh panduan, `amitra.unika.ac.id` hanya contoh domain. Ganti dengan domain yang benar-benar dipakai.

---

## Daftar isi

1. [Gambaran komponen](#1-gambaran-komponen)
2. [Kebutuhan server](#2-kebutuhan-server)
3. [Persiapan di luar server](#3-persiapan-di-luar-server-google-oauth-email-domain)
4. [Instalasi di Linux](#4-instalasi-di-linux)
5. [Instalasi di Windows Server](#5-instalasi-di-windows-server)
6. [Isi file `.env`](#6-isi-file-env)
7. [Inisialisasi aplikasi dan akun superadmin](#7-inisialisasi-aplikasi-dan-akun-superadmin)
8. [Pemeriksaan setelah instalasi](#8-pemeriksaan-setelah-instalasi)
9. [Backup dan pemulihan](#9-backup-dan-pemulihan)
10. [Memperbarui aplikasi](#10-memperbarui-aplikasi)
11. [Mengatasi masalah](#11-mengatasi-masalah)
12. [Serah terima ke LPM](#12-serah-terima-ke-lpm)

---

## 1. Gambaran komponen

```
Pengguna ──HTTPS──▶ Reverse proxy (Nginx di Linux / IIS di Windows)
                        │  /static/  → dilayani langsung dari folder staticfiles
                        │  lainnya   → diteruskan ke 127.0.0.1:8000
                        ▼
                   Aplikasi web AMITRA (gunicorn di Linux / waitress di Windows)
                        │
         ┌──────────────┼──────────────────────┐
         ▼              ▼                      ▼
     PostgreSQL     Redis (antrean)      Folder media (unggahan, PDF)
         ▲              ▲
         └──────────────┴── Worker antrean `qcluster`: membuat PDF/Excel, mengirim email,
                            pengingat tenggat H-3 setiap pukul 07.00, menyegel log audit
```

Ada **dua proses aplikasi yang harus selalu berjalan**:

| Proses | Perintah | Tugas |
|---|---|---|
| Web | gunicorn / waitress | Melayani halaman |
| Worker | `python manage.py qcluster` | PDF, Excel, email, pengingat terjadwal |

Kalau worker mati, website tetap bisa dibuka, tetapi dokumen tidak pernah jadi dan email tidak terkirim. Jadi keduanya harus dipasang sebagai layanan yang otomatis hidup kembali.

**Folder media tidak boleh dibuka langsung dari web.** Semua unduhan berkas lewat aplikasi, yang memeriksa hak akses setiap pengguna. Jangan membuat aturan `/media/` di Nginx atau IIS.

---

## 2. Kebutuhan server

| Komponen | Minimal | Catatan |
|---|---|---|
| CPU / RAM | 2 vCPU / 4 GB | Cukup untuk ±100 unit per periode |
| Disk | 40 GB | Berkas bukti bisa sampai 20 MB per unggahan; pantau pertumbuhan folder media |
| Sistem operasi | Ubuntu 22.04/24.04 LTS, Debian 12, Rocky/AlmaLinux 9, atau Windows Server 2019/2022 | Linux lebih disarankan |
| Python | 3.12 atau lebih baru | Dikembangkan dengan Python 3.14 |
| PostgreSQL | 14 atau lebih baru | Sudah diuji dengan PostgreSQL 18 |
| Redis | 6 atau lebih baru | Untuk Linux. Di Windows boleh tanpa Redis (lihat bagian 5) |
| Pango | — | Pustaka sistem yang dibutuhkan WeasyPrint untuk membuat PDF |
| Sertifikat HTTPS | — | Wajib; login Google tidak bisa memakai HTTP di produksi |
| Port terbuka ke luar | 80 dan 443 saja | PostgreSQL, Redis, dan port 8000 hanya untuk `127.0.0.1` |

---

## 3. Persiapan di luar server (Google OAuth, email, domain)

Bagian ini bisa dikerjakan paralel dengan instalasi server.

### 3.1 Domain dan sertifikat

1. Siapkan subdomain, misalnya `amitra.unika.ac.id`, yang mengarah ke IP server.
2. Siapkan sertifikat HTTPS: sertifikat kampus (wildcard) atau Let's Encrypt.

### 3.2 Login Google (OAuth)

Dikerjakan oleh admin Google Workspace `unika.ac.id`. **Jangan memakai Client ID dari komputer pengembang.**

1. Buka [Google Cloud Console](https://console.cloud.google.com/) dengan akun Workspace kampus, lalu buat project baru, misalnya `AMITRA`.
2. **APIs & Services → OAuth consent screen**:
   - User type **Internal**, agar hanya akun `@unika.ac.id` yang bisa login.
   - Nama aplikasi `AMITRA`, email dukungan email LPM.
   - Scope: `email`, `profile`, `openid`.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Authorized JavaScript origins: `https://amitra.unika.ac.id`
   - Authorized redirect URIs: `https://amitra.unika.ac.id/akun/google/login/callback/` (garis miring di akhir wajib ada).
4. Simpan **Client ID** dan **Client secret**. Keduanya dimasukkan ke `.env` di server (bagian 6). Jangan mengirimnya lewat email atau chat; serahkan langsung kepada orang yang memasang server.

### 3.3 Email keluar (SMTP)

AMITRA mengirim email penugasan, pengingat tenggat, dan dokumen Final. Pilih salah satu:

- **Akun Google Workspace khusus**, misalnya `amitra-noreply@unika.ac.id`: aktifkan verifikasi 2 langkah, buat **App Password**, lalu pakai `smtp.gmail.com` port 587.
- **SMTP relay kampus** atau `smtp-relay.gmail.com` yang diizinkan untuk IP server.

---

## 4. Instalasi di Linux

Contoh perintah untuk **Ubuntu 24.04 LTS** (sama untuk Ubuntu 22.04 dan Debian 12). Perbedaan untuk Rocky/AlmaLinux ada di bagian 4.8.

Tata letak yang dipakai:

| Isi | Lokasi |
|---|---|
| Kode aplikasi | `/opt/amitra/app` |
| Berkas unggahan dan dokumen | `/var/lib/amitra/media` |
| Pengguna sistem yang menjalankan aplikasi | `amitra` |

### 4.1 Paket sistem

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential git \
    postgresql redis-server nginx \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation
python3 --version    # harus 3.12 atau lebih baru
```

Di Ubuntu 22.04 dan Debian 12, Python bawaan adalah 3.10/3.11. Pasang Python 3.12 lebih dulu (misalnya lewat paket `python3.12` dari repositori deadsnakes), lalu pakai `python3.12` menggantikan `python3` pada langkah 4.4.

### 4.2 Pengguna dan folder

```bash
sudo useradd --system --create-home --home-dir /opt/amitra --shell /bin/bash amitra
sudo mkdir -p /var/lib/amitra/media
sudo chown -R amitra:amitra /var/lib/amitra
```

### 4.3 Database PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER amitra WITH PASSWORD 'GANTI-KATA-SANDI-KUAT';"
sudo -u postgres psql -c "CREATE DATABASE amitra OWNER amitra ENCODING 'UTF8';"
```

Pengguna `amitra` harus menjadi **pemilik** database. Migrasi membuat fungsi dan trigger yang membuat log audit tidak bisa diubah atau dihapus, dan itu butuh hak pemilik.

### 4.4 Kode aplikasi dan pustaka Python

```bash
sudo -iu amitra
# Salin kode ke /opt/amitra/app: git clone <alamat-repositori> app, atau ekstrak zip ke folder app
cd /opt/amitra/app
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Perintah ini otomatis memasang **gunicorn** dan driver PostgreSQL. Waitress hanya terpasang di Windows.

### 4.5 File `.env` dan inisialisasi

1. Buat `/opt/amitra/app/.env` sesuai bagian 6, lalu `chmod 600 .env`.
2. Jalankan langkah inisialisasi di bagian 7 sebagai pengguna `amitra`.
3. Keluar dari pengguna `amitra` (`exit`).

### 4.6 Layanan systemd

Buat `/etc/systemd/system/amitra-web.service`:

```ini
[Unit]
Description=AMITRA - aplikasi web
After=network.target postgresql.service

[Service]
User=amitra
Group=amitra
WorkingDirectory=/opt/amitra/app
ExecStart=/opt/amitra/app/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 --workers 3 --timeout 60 --access-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Buat `/etc/systemd/system/amitra-worker.service`:

```ini
[Unit]
Description=AMITRA - worker antrean (PDF, email, pengingat)
After=network.target postgresql.service redis-server.service

[Service]
User=amitra
Group=amitra
WorkingDirectory=/opt/amitra/app
ExecStart=/opt/amitra/app/.venv/bin/python manage.py qcluster
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Aktifkan dan periksa:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now amitra-web amitra-worker
sudo systemctl status amitra-web amitra-worker
journalctl -u amitra-web -u amitra-worker -f     # log galat aplikasi
```

Jumlah `--workers` gunicorn umumnya 2 × jumlah CPU + 1.

### 4.7 Nginx dan HTTPS

Buat `/etc/nginx/sites-available/amitra`:

```nginx
server {
    listen 80;
    server_name amitra.unika.ac.id;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name amitra.unika.ac.id;

    ssl_certificate     /etc/ssl/certs/amitra.crt;     # sesuaikan, atau biarkan certbot mengisi
    ssl_certificate_key /etc/ssl/private/amitra.key;

    client_max_body_size 25m;                          # unggahan bukti maksimal 20 MB

    location /static/ {
        alias /opt/amitra/app/staticfiles/;
        expires 7d;
    }

    # Tidak ada location /media/: berkas hanya diunduh lewat aplikasi (pemeriksaan hak akses).

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Aktifkan:

```bash
sudo ln -s /etc/nginx/sites-available/amitra /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Untuk Let's Encrypt: `sudo apt install -y certbot python3-certbot-nginx`, lalu `sudo certbot --nginx -d amitra.unika.ac.id`.

Nginx harus bisa membaca `/opt/amitra/app/staticfiles`. Bila halaman tampil tanpa gaya, jalankan `sudo chmod o+x /opt/amitra /opt/amitra/app`.

### 4.8 Perbedaan untuk Rocky Linux / AlmaLinux 9

| Langkah | Perintah atau penyesuaian |
|---|---|
| Paket | `sudo dnf install -y python3.12 python3.12-devel gcc git nginx redis postgresql-server pango liberation-serif-fonts` |
| Inisialisasi PostgreSQL | `sudo postgresql-setup --initdb && sudo systemctl enable --now postgresql redis nginx` |
| Autentikasi PostgreSQL | Di `/var/lib/pgsql/data/pg_hba.conf`, ubah metode baris `host ... 127.0.0.1/32` dan `::1/128` dari `ident` menjadi `scram-sha-256`, lalu restart PostgreSQL |
| Virtualenv | `python3.12 -m venv .venv` |
| Konfigurasi Nginx | Simpan sebagai `/etc/nginx/conf.d/amitra.conf` (tanpa sites-enabled) |
| Nama layanan Redis | `redis`, bukan `redis-server`, pada baris `After=` di `amitra-worker.service` |
| SELinux | `sudo setsebool -P httpd_can_network_connect 1` dan `sudo chcon -R -t httpd_sys_content_t /opt/amitra/app/staticfiles` |
| Firewall | `sudo firewall-cmd --permanent --add-service=http --add-service=https && sudo firewall-cmd --reload` |

---

## 5. Instalasi di Windows Server

Untuk Windows Server 2019/2022. Tata letak yang dipakai:

| Isi | Lokasi |
|---|---|
| Kode aplikasi | `C:\amitra\app` |
| Berkas unggahan dan dokumen | `D:\amitra-data\media` (sebaiknya di disk data yang ikut di-backup) |
| Konfigurasi IIS | `C:\amitra\iis` |
| Log layanan | `C:\amitra\log` |

**Redis di Windows:** Redis tidak punya versi resmi untuk Windows. AMITRA tetap bisa berjalan tanpa Redis dengan memakai database PostgreSQL sebagai antrean: cukup kosongkan `REDIS_URL`. Untuk beban LPM cara ini memadai. Bila ingin memakai Redis, pakai Memurai atau Redis di server Linux lain (versi 6 atau lebih baru).

### 5.1 Perangkat lunak

1. **Python 3.12 atau lebih baru** dari python.org. Saat memasang, pilih **Install for all users** dan **Add python.exe to PATH**.
2. **PostgreSQL** (installer EDB) versi 14 atau lebih baru. Catat kata sandi pengguna `postgres`.
3. **MSYS2** dari msys2.org, dipasang di `C:\msys64`. Pustaka Pango di dalamnya dipakai WeasyPrint untuk membuat PDF (perintah pemasangannya di bawah daftar ini).
4. **NSSM** (nssm.cc), untuk menjalankan aplikasi sebagai Windows Service. Salin `nssm.exe` ke `C:\amitra\nssm.exe`.
5. **IIS** dengan modul **URL Rewrite 2.1** dan **Application Request Routing (ARR) 3.0** dari iis.net.
6. **Git for Windows** (opsional, bila kode diambil dari repositori).

Setelah MSYS2 terpasang, buka "MSYS2 MINGW64" lalu jalankan:

```
pacman -S mingw-w64-x86_64-pango
```

### 5.2 Database

Buka **SQL Shell (psql)** sebagai `postgres`:

```sql
CREATE USER amitra WITH PASSWORD 'GANTI-KATA-SANDI-KUAT';
CREATE DATABASE amitra OWNER amitra ENCODING 'UTF8';
```

### 5.3 Kode aplikasi dan pustaka Python

Di PowerShell sebagai Administrator:

```powershell
New-Item -ItemType Directory -Force C:\amitra\app, C:\amitra\iis, C:\amitra\log, D:\amitra-data\media
# Salin atau ekstrak kode ke C:\amitra\app
cd C:\amitra\app
py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
```

Perintah ini otomatis memasang **waitress** dan driver PostgreSQL.

### 5.4 File `.env` dan inisialisasi

1. Buat `C:\amitra\app\.env` sesuai bagian 6, dengan tiga baris khusus Windows berikut.
2. Batasi akses file `.env` hanya untuk Administrator dan akun layanan.
3. Jalankan langkah inisialisasi di bagian 7 (dengan `.venv\Scripts\python`).

Baris khusus Windows di `.env`:

```ini
WEASYPRINT_DLL_DIRECTORIES=C:\msys64\mingw64\bin
MEDIA_ROOT=D:\amitra-data\media
REDIS_URL=
```

### 5.5 Layanan Windows dengan NSSM

```powershell
cd C:\amitra

# Aplikasi web (waitress)
.\nssm.exe install amitra-web C:\amitra\app\.venv\Scripts\waitress-serve.exe
.\nssm.exe set amitra-web AppParameters "--listen=127.0.0.1:8000 --threads=8 --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto --no-clear-untrusted-proxy-headers config.wsgi:application"
.\nssm.exe set amitra-web AppDirectory C:\amitra\app
.\nssm.exe set amitra-web AppStdout C:\amitra\log\web.log
.\nssm.exe set amitra-web AppStderr C:\amitra\log\web.log
.\nssm.exe set amitra-web Start SERVICE_AUTO_START

# Worker antrean
.\nssm.exe install amitra-worker C:\amitra\app\.venv\Scripts\python.exe
.\nssm.exe set amitra-worker AppParameters "manage.py qcluster"
.\nssm.exe set amitra-worker AppDirectory C:\amitra\app
.\nssm.exe set amitra-worker AppStdout C:\amitra\log\worker.log
.\nssm.exe set amitra-worker AppStderr C:\amitra\log\worker.log
.\nssm.exe set amitra-worker Start SERVICE_AUTO_START

Start-Service amitra-web, amitra-worker
Get-Service amitra-*
```

**Opsi `--trusted-proxy` wajib ada.** Tanpa opsi itu, waitress membuang header `X-Forwarded-Proto` dari IIS, sehingga aplikasi mengira semua koneksi HTTP: halaman terus dialihkan ke HTTPS dan login Google gagal. Opsi `--no-clear-untrusted-proxy-headers` membiarkan header `X-Forwarded-For` sampai ke aplikasi, agar IP pengguna tercatat di log audit.

Secara bawaan, layanan berjalan sebagai Local System. Bila memakai akun layanan khusus (`nssm set amitra-web ObjectName ...`), pastikan akun itu punya hak tulis ke folder media dan folder log.

### 5.6 IIS sebagai reverse proxy HTTPS

1. **Aktifkan proxy ARR:** IIS Manager → klik nama server → **Application Request Routing Cache** → **Server Proxy Settings** → centang **Enable proxy** → Apply. Biarkan "Preserve client IP in the following header: X-Forwarded-For" tercentang.
2. **Pertahankan header Host** agar domain asli sampai ke aplikasi. Jalankan di PowerShell Administrator: `& "$env:windir\system32\inetsrv\appcmd.exe" set config -section:system.webServer/proxy -preserveHostHeader:true /commit:apphost`
3. **Izinkan variabel server:** IIS Manager → nama server → **URL Rewrite** → **View Server Variables** → **Add** `HTTP_X_FORWARDED_PROTO`.
4. **Buat situs:** Sites → Add Website:
   - Nama `AMITRA`, physical path `C:\amitra\iis`.
   - Binding `https`, port 443, host name `amitra.unika.ac.id`, pilih sertifikat. Tambahkan juga binding `http` port 80.
5. **Folder static:** klik kanan situs AMITRA → **Add Virtual Directory** → alias `static`, physical path `C:\amitra\app\staticfiles`.
6. **Buat `C:\amitra\iis\web.config`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="HTTP ke HTTPS" stopProcessing="true">
          <match url="(.*)" />
          <conditions><add input="{HTTPS}" pattern="off" /></conditions>
          <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
        </rule>
        <rule name="Static dilayani IIS" stopProcessing="true">
          <match url="^static/.*" />
          <action type="None" />
        </rule>
        <rule name="Teruskan ke AMITRA" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <!-- Unggahan bukti maksimal 20 MB -->
        <requestLimits maxAllowedContentLength="26214400" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

Tidak ada aturan untuk `/media/`, dan itu disengaja: berkas hanya diunduh lewat aplikasi.

7. **Firewall Windows:** buka port 80 dan 443 saja. Port 8000 dan PostgreSQL (5432) tidak boleh dibuka ke luar.

---

## 6. Isi file `.env`

File `.env` diletakkan di folder aplikasi (`/opt/amitra/app/.env` atau `C:\amitra\app\.env`). Contoh lengkapnya ada di `.env.example`. File ini berisi rahasia: **jangan dikirim lewat email, jangan di-commit, dan simpan salinannya di tempat aman.**

```ini
SECRET_KEY=<hasil perintah di bawah>
DEBUG=False
ALLOWED_HOSTS=amitra.unika.ac.id
SITUS_URL=https://amitra.unika.ac.id
CSRF_TRUSTED_ORIGINS=https://amitra.unika.ac.id
PERCAYA_PROXY=True

DATABASE_URL=postgres://amitra:GANTI-KATA-SANDI-KUAT@127.0.0.1:5432/amitra

DOMAIN_EMAIL_KAMPUS=unika.ac.id
GOOGLE_CLIENT_ID=<dari bagian 3.2>
GOOGLE_CLIENT_SECRET=<dari bagian 3.2>

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=amitra-noreply@unika.ac.id
EMAIL_HOST_PASSWORD=<App Password>
DEFAULT_FROM_EMAIL=AMITRA LPM <amitra-noreply@unika.ac.id>

# Linux: redis://127.0.0.1:6379/0 — Windows tanpa Redis: kosongkan
REDIS_URL=redis://127.0.0.1:6379/0
Q_WORKERS=2

MEDIA_ROOT=/var/lib/amitra/media
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=0
LOG_LEVEL=WARNING
```

Membuat `SECRET_KEY` baru (wajib berbeda untuk setiap server):

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Penjelasan variabel yang sering keliru:

| Variabel | Fungsi |
|---|---|
| `DEBUG` | Harus `False` di produksi. Bila `True`, pesan galat lengkap tampil ke pengguna |
| `PERCAYA_PROXY` | `True` karena aplikasi berada di belakang Nginx/IIS. Tanpa ini, login Google gagal dengan `redirect_uri_mismatch` |
| `DOMAIN_EMAIL_KAMPUS` | Hanya email dari domain ini yang boleh login lewat Google |
| `SITUS_URL` | Dipakai untuk tautan di email; harus alamat HTTPS publik |
| `SECURE_HSTS_SECONDS` | Biarkan `0` sampai HTTPS stabil beberapa minggu, lalu isi `31536000`. HSTS sulit dibatalkan setelah aktif di browser pengguna |

---

## 7. Inisialisasi aplikasi dan akun superadmin

Jalankan dari folder aplikasi dengan Python di `.venv`. Di Linux pakai `.venv/bin/python`, di Windows `.venv\Scripts\python`.

```bash
python manage.py migrate                 # membuat tabel, tipe unit, dan trigger log audit
python manage.py collectstatic --noinput # menyalin CSS/JS/logo ke folder staticfiles
python manage.py isi_data_contoh --paksa # Tujuan Audit, kategori surat, pola nomor surat, nomor formulir
python manage.py pasang_jadwal           # jadwal pengingat H-3 (07.00) dan penyegelan log (10 menit)
python manage.py createsuperuser         # akun superadmin pertama
python manage.py check --deploy          # pemeriksaan keamanan
```

Catatan:

- **`isi_data_contoh`** mengisi data awal yang wajar (Tujuan Audit a–f, kategori surat, pola nomor surat). LPM tetap perlu memeriksa dan menyesuaikannya lewat menu Administrasi.
- **Jangan menjalankan `isi_data_demo`** di server produksi. Perintah itu membuat akun dan audit fiktif dengan kata sandi yang diketahui umum, dan memang menolak berjalan bila `DEBUG=False`.
- **`check --deploy`** boleh menyisakan satu peringatan `security.W004` (HSTS) selama `SECURE_HSTS_SECONDS=0`.

### Akun superadmin

`createsuperuser` hanya menanyakan **email** dan **kata sandi**. Akun yang dibuat otomatis berperan **Master Admin LPM**.

- Gunakan email resmi LPM, misalnya email Kepala LPM.
- Kata sandi diketik langsung saat perintah dijalankan, sebaiknya oleh perwakilan LPM sendiri. **Jangan dikirim lewat email atau chat.**
- Superadmin bisa masuk dengan email dan kata sandi lewat bagian **Masuk sebagai tamu**. Bila emailnya `@unika.ac.id`, ia juga bisa masuk dengan tombol Google dan akunnya otomatis tersambung.
- Staf LPM lain tidak perlu dibuatkan akun dari server. Mereka cukup login dengan Google, lalu superadmin memberi peran **Master Admin LPM** atau **Admin LPM** di menu Administrasi → Pengguna.

---

## 8. Pemeriksaan setelah instalasi

| No | Periksa | Hasil yang benar |
|---|---|---|
| 1 | Buka `https://amitra.unika.ac.id/` | Halaman **Masuk ke AMITRA** tampil berwarna ungu dengan logo (berarti static terlayani) |
| 2 | Buka `http://amitra.unika.ac.id/` | Dialihkan ke `https://` |
| 3 | Masuk sebagai superadmin | Masuk ke halaman Tugas Saya; menu Administrasi ada di sidebar |
| 4 | Masuk dengan Google memakai akun `@unika.ac.id` lain | Muncul halaman "Akun Anda menunggu penetapan peran" (normal untuk akun baru) |
| 5 | Masuk dengan Google memakai akun Gmail pribadi | Ditolak, oleh Google (consent screen Internal) atau oleh AMITRA (domain tidak diizinkan) |
| 6 | Buka `https://amitra.unika.ac.id/media/` | **404** (folder media tidak boleh terbuka) |
| 7 | Administrasi → Django Q → Scheduled tasks | Ada `pengingat-harian` dan `segel-log` |
| 8 | Setelah 10–15 menit: Administrasi → Django Q → Successful tasks | Ada tugas `segel-log` yang berhasil (worker hidup) |
| 9 | `python manage.py sendtestemail alamat-anda@unika.ac.id` | Email uji diterima |
| 10 | Uji pustaka PDF: `python -c "from weasyprint import HTML; HTML(string='<p>uji</p>').write_pdf('uji.pdf')"` | File `uji.pdf` terbentuk (hapus setelahnya) |
| 11 | `python manage.py periksa_log` | Tidak ada masalah pada rantai log audit |

---

## 9. Backup dan pemulihan

Yang wajib di-backup setiap hari:

1. **Database PostgreSQL**: semua data audit, pengguna, dan log.
2. **Folder media**: bukti unggahan, PDF/Excel, scan bertanda tangan.
3. **File `.env`**: cukup sekali dan setiap kali berubah; simpan terpisah dan terenkripsi.

Database tanpa folder media, atau sebaliknya, tidak bisa dipulihkan dengan utuh. Backup keduanya pada waktu yang berdekatan.

### Linux (cron)

Buat `/etc/cron.d/amitra-backup`:

```cron
# Setiap hari pukul 01.30: dump database, salin media, hapus backup lebih dari 30 hari
30 1 * * * amitra pg_dump -Fc -d amitra -f /var/backups/amitra/db-$(date +\%F).dump && rsync -a --delete /var/lib/amitra/media/ /var/backups/amitra/media/ && find /var/backups/amitra -name 'db-*.dump' -mtime +30 -delete
```

Siapkan foldernya dengan `sudo mkdir -p /var/backups/amitra && sudo chown amitra:amitra /var/backups/amitra`. `pg_dump` tidak meminta kata sandi karena PostgreSQL mengenali pengguna sistem `amitra` sebagai peran database `amitra` (autentikasi *peer* lewat socket lokal). Salin folder `/var/backups/amitra` ke server atau penyimpanan lain secara berkala.

### Windows (Task Scheduler)

Buat `C:\amitra\backup.ps1`:

```powershell
$tgl = Get-Date -Format "yyyy-MM-dd"
$env:PGPASSWORD = "GANTI-KATA-SANDI-KUAT"
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h 127.0.0.1 -U amitra -Fc -d amitra -f "E:\backup-amitra\db-$tgl.dump"
robocopy D:\amitra-data\media E:\backup-amitra\media /MIR /R:2 /W:5 /NP
Get-ChildItem E:\backup-amitra\db-*.dump | Where-Object LastWriteTime -lt (Get-Date).AddDays(-30) | Remove-Item
```

Sesuaikan versi PostgreSQL di jalurnya. Lalu jadwalkan di Task Scheduler: setiap hari pukul 01.30, jalankan `powershell.exe -ExecutionPolicy Bypass -File C:\amitra\backup.ps1` dengan akun yang punya akses ke folder backup.

### Memulihkan

1. Hentikan layanan web dan worker.
2. Buat database kosong baru dengan pemilik `amitra` (bagian 4.3 / 5.2).
3. `pg_restore -h 127.0.0.1 -U amitra -d amitra --no-owner db-YYYY-MM-DD.dump`
4. Kembalikan isi folder media dari backup tanggal yang sama.
5. Jalankan layanan, lalu `python manage.py periksa_log`.

---

## 10. Memperbarui aplikasi

Saat LPM mengirim versi baru:

1. Backup database dan folder media (bagian 9).
2. Hentikan layanan: `sudo systemctl stop amitra-web amitra-worker` (Linux) atau `Stop-Service amitra-web, amitra-worker` (Windows).
3. Ganti kode: `git pull`, atau ekstrak zip baru di atas folder aplikasi. **Jangan menimpa atau menghapus `.env` dan folder media.**
4. Jalankan perintah pembaruan di bawah ini dari folder aplikasi.
5. Jalankan kembali layanan web dan worker.

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py pasang_jadwal
python manage.py check --deploy
```

---

## 11. Mengatasi masalah

| Gejala | Penyebab umum | Solusi |
|---|---|---|
| Google menampilkan `redirect_uri_mismatch` | Alamat callback berbeda dengan yang didaftarkan, atau aplikasi mengira koneksinya HTTP | Pastikan redirect URI persis `https://<domain>/akun/google/login/callback/`; `PERCAYA_PROXY=True`; proxy mengirim `X-Forwarded-Proto` |
| Login Google ditolak untuk akun kampus | `DOMAIN_EMAIL_KAMPUS` salah | Isi `unika.ac.id`, lalu restart layanan web |
| `Bad Request (400)` | Domain tidak ada di `ALLOWED_HOSTS`, atau IIS tidak meneruskan Host asli | Periksa `ALLOWED_HOSTS`; di IIS jalankan perintah `preserveHostHeader` (5.6 langkah 2) |
| `403 CSRF verification failed` saat menyimpan formulir | Origin HTTPS tidak dikenali | Isi `CSRF_TRUSTED_ORIGINS=https://<domain>` dan pastikan `X-Forwarded-Proto` terkirim |
| Halaman terus dialihkan (redirect loop) | `SECURE_SSL_REDIRECT=True` tetapi `X-Forwarded-Proto: https` tidak sampai ke aplikasi | Periksa header di proxy. Di Windows, pastikan parameter waitress memuat `--trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto` (5.5). Sementara bisa `SECURE_SSL_REDIRECT=False` |
| Halaman tampil polos tanpa warna | Static belum dikumpulkan atau tidak terlayani | `collectstatic`; periksa `alias` Nginx atau virtual directory IIS |
| Dokumen berstatus "Diantre" terus, muncul peringatan antrean tertahan | Worker `qcluster` tidak berjalan | Jalankan/restart layanan `amitra-worker`; periksa lognya |
| Dokumen berstatus "Gagal" dengan pesan Pango/GTK | Pustaka Pango tidak ditemukan | Linux: pasang paket di 4.1. Windows: pasang Pango lewat MSYS2 dan isi `WEASYPRINT_DLL_DIRECTORIES` |
| Worker galat `unknown command HELLO` | Versi Redis di bawah 6 | Pakai Redis 6 atau lebih baru (atau tambahkan `?protocol=2` di akhir `REDIS_URL` sebagai solusi sementara) |
| Email tidak terkirim | SMTP salah atau worker mati | Uji dengan `sendtestemail`; periksa log worker |
| Unggahan bukti gagal `413` | Batas ukuran di proxy terlalu kecil | Nginx `client_max_body_size 25m`; IIS `maxAllowedContentLength` |
| Galat saat `migrate` tentang fungsi atau trigger | Pengguna database bukan pemilik database | `ALTER DATABASE amitra OWNER TO amitra;` lalu ulangi |

Lokasi log: Linux `journalctl -u amitra-web -u amitra-worker`; Windows `C:\amitra\log\web.log` dan `worker.log`.

---

## 12. Serah terima ke LPM

Setelah pemeriksaan di bagian 8 lulus, serahkan kepada LPM:

1. Alamat aplikasi (`https://amitra.unika.ac.id`).
2. Email akun superadmin. Kata sandinya diketik sendiri oleh perwakilan LPM saat `createsuperuser`, atau diganti saat pertama kali masuk.
3. Kontak BMSI untuk gangguan server.

LPM lalu melanjutkan dengan **Tahap 0: Persiapan** di `docs/PANDUAN-ALUR-AUDIT.md`: mengaktifkan pengguna, mengisi unit, membuat periode, menyiapkan standar, dan memplot audit.
