"""Bangun CSS Tailwind dengan CLI standalone, tanpa Node.

    python scripts/tailwind.py           # sekali, minified
    python scripts/tailwind.py --watch   # selama development

Binary diunduh sekali ke .bin/ dan dicek dengan sha256sums.txt rilis yang sama.
"""

import hashlib
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSI = "v4.3.3"
AKAR = Path(__file__).resolve().parent.parent
MASUKAN = AKAR / "assets" / "css" / "app.css"
KELUARAN = AKAR / "static" / "css" / "app.css"
URL_RILIS = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{VERSI}"


def nama_aset():
    sistem = platform.system().lower()
    mesin = platform.machine().lower()
    arsitektur = "arm64" if mesin in ("arm64", "aarch64") else "x64"
    if sistem == "windows":
        return f"tailwindcss-windows-{arsitektur}.exe"
    if sistem == "darwin":
        return f"tailwindcss-macos-{arsitektur}"
    return f"tailwindcss-linux-{arsitektur}"


def pastikan_binary():
    aset = nama_aset()
    tujuan = AKAR / ".bin" / f"{VERSI}-{aset}"
    if tujuan.exists():
        return tujuan
    tujuan.parent.mkdir(exist_ok=True)
    print(f"Mengunduh {aset} {VERSI} ...")
    with urllib.request.urlopen(f"{URL_RILIS}/sha256sums.txt") as r:
        daftar = r.read().decode()
    harapan = next((b.split()[0] for b in daftar.splitlines() if b.strip().endswith(aset)), None)
    if harapan is None:
        sys.exit(f"Checksum untuk {aset} tidak ditemukan di rilis {VERSI}.")
    with urllib.request.urlopen(f"{URL_RILIS}/{aset}") as r:
        isi = r.read()
    if hashlib.sha256(isi).hexdigest() != harapan:
        sys.exit("Checksum binary Tailwind tidak cocok; unduhan dibatalkan.")
    tujuan.write_bytes(isi)
    tujuan.chmod(0o755)
    return tujuan


def main():
    perintah = [str(pastikan_binary()), "-i", str(MASUKAN), "-o", str(KELUARAN)]
    perintah += ["--watch"] if "--watch" in sys.argv else ["--minify"]
    sys.exit(subprocess.call(perintah, cwd=AKAR))


if __name__ == "__main__":
    main()
