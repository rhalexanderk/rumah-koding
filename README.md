# Rumah Koding

Rumah Koding adalah platform belajar coding interaktif berbasis web (Flask) tempat siswa bisa belajar bahasa pemrograman (Python & JavaScript) serta Web Automation lewat modul-modul yang dilengkapi editor kode, eksekusi kode langsung di browser, sistem progres belajar, leaderboard, dan panel admin untuk mengelola materi serta data siswa.

## ✨ Fitur Utama

- **Autentikasi Pengguna**
  - Login & registrasi siswa (dengan CAPTCHA matematika sederhana untuk mencegah bot)
  - Role-based access: `admin` dan `student`
  - Password di-hash menggunakan `werkzeug.security`
  - Proteksi CSRF global via `Flask-WTF`

- **Modul Belajar Reguler (Python & JavaScript)**
  - Katalog kursus per bahasa pemrograman
  - Editor kode interaktif dengan eksekusi kode langsung (AJAX)
  - Validasi keamanan kode Python menggunakan `ast` (memblokir modul berbahaya seperti `os`, `sys`, `subprocess`, dsb, serta fungsi seperti `eval`, `exec`)
  - Validasi keamanan kode JavaScript (memblokir `require('fs')`, `child_process`, `process.exit`, dsb)
  - Timeout eksekusi kode (maks. 3 detik) untuk mencegah infinite loop
  - Pengecekan jawaban otomatis dengan normalisasi output
  - Tracking progres belajar per modul (`belum`, `sedang_belajar`, `selesai`)

- **Modul Web Automation**
  - Jalur belajar terpisah dengan tabel & progres sendiri
  - Workspace interaktif per modul otomasi

- **Dashboard Siswa**
  - Statistik ringkasan progres belajar keseluruhan (reguler + automation)

- **Halaman Profil**
  - Update username/password
  - Progres belajar per bahasa

- **Leaderboard**
  - Papan peringkat 10 siswa dengan modul terbanyak diselesaikan

- **Panel Admin (Studio Admin)**
  - CRUD materi/modul pembelajaran
  - CRUD data siswa (tambah, edit, hapus akun)
  - Kontrol manual status progres modul siswa

## 🛠️ Tech Stack

| Komponen        | Teknologi                     |
|------------------|--------------------------------|
| Backend          | Python, Flask                 |
| Database         | SQLite (`rumah_koding.db`)    |
| Keamanan         | Flask-WTF (CSRF), Werkzeug (hashing), `ast` (sandbox validasi kode Python) |
| Eksekusi Kode    | `subprocess` — `python` untuk kode Python, `node` untuk kode JavaScript |
| Frontend         | Jinja2 Templates (folder `templates/`), aset statis (folder `static/`) |

## 📁 Struktur Proyek

```
rumah-koding/
├── app.py              # Entry point aplikasi Flask (routes, logic, init DB)
├── rumah_koding.db      # Database SQLite (dibuat/diisi otomatis oleh init_db())
├── templates/           # Template HTML (Jinja2)
└── static/              # File statis (CSS, JS, gambar, dsb)
```

## ⚙️ Prasyarat

- Python 3.9+
- **Node.js** terpasang di sistem dan tersedia di `PATH` (dipakai oleh aplikasi untuk mengeksekusi kode JavaScript siswa via `subprocess.run(["node", ...])`)
- `python` sebagai perintah yang bisa dipanggil di `PATH` (dipakai untuk mengeksekusi kode Python siswa)

## 🚀 Instalasi & Menjalankan

1. **Clone repository**
   ```bash
   git clone https://github.com/rhalexanderk/rumah-koding.git
   cd rumah-koding
   ```

2. **Buat virtual environment (opsional tapi disarankan)**
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux/Mac
   venv\Scripts\activate         # Windows
   ```

3. **Install dependencies Python**
   ```bash
   pip install -r requirements.txt
   ```

4. **Pastikan Node.js terpasang** (untuk menjalankan kode JavaScript siswa)
   ```bash
   node -v
   ```

5. **Jalankan aplikasi**
   ```bash
   python app.py
   ```
   > Catatan: `app.py` saat ini belum memiliki blok `if __name__ == "__main__": app.run(...)` yang terlihat pada bagian awal file — jika Anda menambahkannya, jalankan dengan `app.run(debug=True)`. Alternatif lain, jalankan lewat Flask CLI:
   ```bash
   flask --app app run --debug
   ```

6. Buka browser ke `http://127.0.0.1:5000`

## 🔑 Akun Default

Saat pertama kali dijalankan, `init_db()` otomatis membuat akun admin default:

- **Username:** `admin`
- **Password:** `admin123`

> ⚠️ **Penting:** Segera ganti password admin default ini setelah instalasi pertama, terutama jika aplikasi di-deploy ke lingkungan publik.

## 🔒 Catatan Keamanan

- `SECRET_KEY` di dalam `app.py` saat ini di-hardcode langsung di source code. Untuk penggunaan produksi, sebaiknya pindahkan ke environment variable (misalnya lewat `python-dotenv` atau `os.environ`) dan jangan commit secret ke repository publik.
- Eksekusi kode siswa dilakukan di server menggunakan `subprocess` dengan validasi `ast` (Python) dan pengecekan string sederhana (JavaScript). Ini membantu memblokir sebagian pola berbahaya, namun **bukan sandbox yang sepenuhnya aman**. Untuk deployment produksi/publik, pertimbangkan menjalankan eksekusi kode di container terisolasi (misalnya Docker, gVisor, atau layanan sandbox pihak ketiga) dengan batasan CPU/memori/network yang lebih ketat.

## 📄 Lisensi

Belum ditentukan oleh pemilik repository. Silakan hubungi pemilik repo (`rhalexanderk`) untuk informasi lisensi.
