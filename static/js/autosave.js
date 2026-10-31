// Autosave bersama untuk SER dan penilaian auditor (FR-20, NFR-05).
//
// Pemakaian: x-data="SIAMI.autosave('id-json-konfig', ['penjelasan'])"
// Konfig (json_script): {bisa_ubah, pk, url, csrf, versi, waktu, data: {kolom: nilai}}
// Server membalas 200 {versi, waktu, lengkap} atau 409 {pesan, versi, waktu, oleh, data}.
window.SIAMI = window.SIAMI || {};

window.SIAMI.autosave = function (idKonfig, kolom) {
  const k = JSON.parse(document.getElementById(idKonfig).textContent);
  const awal = {};
  kolom.forEach((n) => { awal[n] = (k.data && k.data[n]) || ""; });

  return {
    ...awal,
    versi: k.versi, waktu: k.waktu,
    kotor: false, status: "tersimpan", pesan: "", konflik: {},

    init() {
      if (!k.bisa_ubah) return;
      setInterval(() => this.simpan(), 30000); // tiap 30 detik bila ada perubahan
      window.addEventListener("beforeunload", (e) => { if (this.kotor) e.preventDefault(); });
    },

    tandaiKotor() {
      this.kotor = true;
      if (this.status !== "konflik") this.status = "belum";
    },

    async simpan() {
      if (!k.bisa_ubah || !this.kotor) return true;
      if (this.status === "konflik" || this.status === "menyimpan") return false;
      this.status = "menyimpan";
      const data = new FormData();
      kolom.forEach((n) => data.append(n, this[n]));
      data.append("versi", this.versi);
      let r;
      try {
        r = await fetch(k.url, { method: "POST", body: data, headers: { "X-CSRFToken": k.csrf } });
      } catch (e) {
        this.status = "gagal";
        this.pesan = "Gagal menyimpan. Periksa koneksi internet Anda.";
        return false;
      }
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        this.versi = d.versi; this.waktu = d.waktu; this.kotor = false; this.status = "tersimpan";
        this.tanda(d.lengkap);
        return true;
      }
      if (r.status === 409) { this.status = "konflik"; this.konflik = d; return false; }
      this.status = "gagal";
      this.pesan = d.pesan || "Gagal menyimpan.";
      return false;
    },

    pakaiVersiServer() {
      kolom.forEach((n) => { this[n] = (this.konflik.data && this.konflik.data[n]) || ""; });
      this.versi = this.konflik.versi; this.waktu = this.konflik.waktu;
      this.kotor = false; this.status = "tersimpan";
    },

    timpa() {
      this.versi = this.konflik.versi; this.status = "belum"; this.kotor = true;
      this.simpan();
    },

    tanda(lengkap) {
      const el = document.getElementById("tanda-" + k.pk);
      if (!el) return;
      el.classList.toggle("bg-green-600", !!lengkap);
      el.classList.toggle("bg-slate-300", !lengkap);
      el.setAttribute("aria-label", lengkap ? "Lengkap" : "Belum lengkap");
      el.setAttribute("title", lengkap ? "Lengkap" : "Belum lengkap");
    },

    // Simpan dulu saat pindah butir; tetap di tempat bila gagal.
    async pindah(url) {
      if (await this.simpan()) { this.kotor = false; window.location = url; }
    },
  };
};
