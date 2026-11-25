# ⚡ YutoVNC - Smart Remote Client

**YutoVNC** adalah aplikasi desktop Windows modern dan ringan untuk mengelola puluhan hingga ratusan perangkat remote VNC secara terpusat dengan fitur **1-Klik Langsung Masuk (Auto-Login)**, pemantauan status Online/Offline (TCP Port 5900), multi-sesi berbasis tab, dan keamanan password menggunakan Windows DPAPI.

---

## ✨ Fitur Utama

### 1. Manajemen Host & Address Book (CRUD & Grouping)
- **Data Lengkap:** Simpan Nama Alias/Ruangan, Alamat IP, Port (default `5900`), Grup/Kategori, Password VNC, Mode Tampilan (*View-Only / Full Screen / Scaling*), dan Catatan.
- **Instant Search:** Pencarian cepat *real-time* berdasarkan nama alias, IP, kategori, atau catatan saat Anda mengetik.
- **Kategori & Grup Sidebar:** Pengelompokan perangkat (misal: *Server IT, Lab Komputer, Kasir/POS*) lengkap dengan jumlah perangkat dan tab Favorit ⭐.

### 2. Koneksi 1-Klik & Auto-Login
- **1-Click Connect:** Cukup klik ganda pada baris komputer, aplikasi langsung menginjeksi password dan membuka sesi remote secara otomatis tanpa perlu mengetik ulang password.
- **Status Monitor (Port 5900):** Pemantauan *real-time* di latar belakang dengan indikator visual:
  - 🟢 **Online** (Port terbuka + latensi respons dalam milidetik, misal `12 ms`)
  - 🔴 **Offline** (Port tertutup / Timeout / Host tidak terjangkau)
- **Auto-Refresh:** Pilihan interval auto-refresh (10s, 15s, 30s, 60s, atau manual).

### 3. Multi-Session (Tab) & Quick Toolbar
- **Embedded Viewer:** Membuka beberapa layar remote sekaligus dalam bentuk tab rapi di dalam satu jendela aplikasi (menggunakan Win32 API docking).
- **Toolbar Pintas di Setiap Tab:**
  - ⚡ **Ctrl+Alt+Del:** Kirim sinyal CAD ke komputer remote dengan 1 klik.
  - 📸 **Screenshot:** Ambil tangkapan layar sesi remote seketika dan simpan otomatis di folder `screenshots/`.
  - 🔲 **Scale to Fit:** Sesuaikan ukuran layar remote secara responsif.
  - 👁️ **View-Only:** Tombol toggle mode hanya lihat (mencegah input keyboard/mouse tak sengaja).
  - 🔄 **Reconnect:** Sambung ulang cepat jika koneksi terputus.
  - ↗️ **Pop Out:** Lepas sesi dari tab menjadi jendela independen kapan saja.
  - ❌ **Disconnect:** Akhiri sesi dengan aman.

### 4. Keamanan & Portabilitas
- **Enkripsi Windows DPAPI:** Password disimpan dalam database lokal dengan enkripsi tingkat OS Windows (`CryptProtectData`), sehingga aman dan tidak tersimpan dalam bentuk teks biasa.
- **Backup & Migrasi (JSON / CSV / .vnc):**
  - Ekspor/Impor format JSON lengkap dengan opsi proteksi **Master Password**.
  - Ekspor/Impor format CSV untuk memudahkan pengisian massal puluhan PC lewat Microsoft Excel.
  - Migrasi file `.vnc` lama langsung ke dalam address book.
- **100% Portable:** Database SQLite berkecepatan tinggi (`yutovnc.db`) tersimpan langsung di folder aplikasi tanpa perlu instalasi rumit.

### 5. Ringan & Cepat (Non-Functional Requirements)
- **Startup:** < 0.5 detik.
- **Konsumsi RAM:** ~25 - 35 MB (jauh di bawah batas 100 MB).
- **Kompatibilitas:** Mendukung TightVNC, TigerVNC, UltraVNC, dan RealVNC viewer.

---

## 🚀 Cara Menjalankan

### Opsi 1: Menjalankan Aplikasi Hasil Build (.exe Standalone)
Jika Anda sudah menjalankan `build.bat`, aplikasi sudah siap pakai tanpa Python:
- Buka folder `dist\YutoVNC\` dan klik ganda **`YutoVNC.exe`**.

### Opsi 2: Menjalankan Script Portable (Mode Development)
- Klik ganda **`YutoVNC.vbs`** (Membuka aplikasi tanpa jendela konsol hitam), atau
- Klik ganda **`YutoVNC.bat`**, atau
- Lewat terminal: `python main.py`

---

## 🔨 Pipeline Build & Pembuatan Installer Windows

### 1. Build Executable Standalone (`dist\YutoVNC\YutoVNC.exe`)
Cukup jalankan file batch:
```cmd
build.bat
```
Script `build.bat` akan secara otomatis:
1. Memeriksa keberadaan Python dan PyInstaller (menginstall via pip jika belum ada).
2. Membundel `tvnviewer.exe` ke folder `bin\` agar paket mandiri tanpa mengharuskan TightVNC diinstal terpisah di PC target.
3. Mengompilasi aplikasi menggunakan `YutoVNC.spec` dalam mode `--windowed` (`--noconsole`) dengan ikon multi-resolusi `assets\icon.ico`.
4. Menghasilkan folder siap distribusi: `dist\YutoVNC\`.

### 2. Membuat Setup Installer Tunggal (`Setup_YutoVNC.exe`)
Installer dibuat menggunakan **Inno Setup** berdasarkan script `installer.iss`:
- Jika Inno Setup sudah terinstall di komputer, `build.bat` akan **otomatis** memanggil `ISCC.exe` untuk menghasilkan `Output\Setup_YutoVNC.exe`.
- Atau Anda dapat membuka file [installer.iss](file:///c:/Users/Yulli/OneDrive/Documents/Yuto/YutoVNC/installer.iss) langsung dengan Inno Setup Compiler dan menekan tombol **Compile / Run (F9)**.
- **Fitur Installer:**
  - Terinstall otomatis ke `C:\Program Files\YutoVNC` (atau `%LocalAppData%` untuk opsi non-admin).
  - Pilihan shortcut di Desktop dan Start Menu.
  - Database, konfigurasi, dan screenshot aman disimpan di `%APPDATA%\YutoVNC` sehingga bebas dari kendala izin tulis (*permission error*).
  - Uninstaller bersih dan terdaftar di *Windows Settings > Installed Apps*.

---

## 📁 Struktur Proyek
```
YutoVNC/
├── yutovnc/
│   ├── __init__.py
│   ├── security.py          # Enkripsi DPAPI & Master Password AES/PBKDF2
│   ├── models.py            # Dataclass Host, Status, AppSettings
│   ├── database.py          # SQLite database manager (WAL mode, CRUD, search)
│   ├── monitor.py           # Background TCP 5900 probe & latency measurement
│   ├── vnc_launcher.py      # TightVNC auto-login & Win32 window docking
│   ├── exporter.py          # Import/Export JSON, CSV, dan migrasi file .vnc
│   ├── theme.py             # Dark & Light modern theme styles
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py   # Jendela utama, sidebar grup, address book table
│       ├── host_dialog.py   # Modal Tambah/Edit host + tes koneksi on-the-fly
│       ├── settings_dialog.py # Pengaturan engine VNC, mode tab, interval cek
│       ├── import_export_dialog.py # Dialog backup/restore & download template
│       └── session_tab.py   # Tab remote session + Quick Toolbar (CAD, Screenshot)
├── tests/                   # Unit test suite lengkap
│   ├── test_security.py
│   ├── test_database.py
│   ├── test_vnc_launcher.py
│   ├── test_exporter.py
│   └── test_monitor.py
├── main.py                  # Entry point aplikasi & initial demo data seeder
├── YutoVNC.bat              # Windows batch launcher
├── YutoVNC.vbs              # Silent background launcher
└── README.md                # Dokumentasi & panduan pengguna
```

---

## 🧪 Menjalankan Unit Test
Untuk memverifikasi seluruh komponen bekerja sempurna:
```powershell
python -m unittest discover tests
```
Semua 13 unit test mencakup enkripsi, database, pembuatan argumen launcher, import/export data, dan status monitor.
