"""Import & Export Dialog for YutoVNC."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from typing import Optional, Callable
from yutovnc.database import Database
from yutovnc.exporter import DataExporter
from yutovnc.theme import get_theme_colors

class ImportExportDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        db: Database,
        on_data_changed: Optional[Callable[[], None]] = None,
        theme_name: str = "dark"
    ):
        super().__init__(parent)
        self.db = db
        self.on_data_changed = on_data_changed
        self.colors = get_theme_colors(theme_name)

        self.title("📁 Backup, Import & Export Data Host")
        self.geometry("580x500")
        self.minsize(520, 440)
        self.configure(bg=self.colors["surface"])
        self.transient(parent)
        self.grab_set()

        self._init_ui()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = 580
        h = min(500, max(440, sh - 90))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_ui(self):
        header = ttk.Frame(self, style="Surface.TFrame", padding=(20, 16, 20, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Manajemen Data & Backup", style="Title.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(header, text="Ekspor / Impor konfigurasi host remote (JSON terenkripsi, CSV, file .vnc).", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(2, 0))

        # Tabbed notebook for Export vs Import vs Template
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=16, pady=10)

        # Tab 1: Export
        export_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=16)
        notebook.add(export_tab, text="📤 Ekspor Data")
        self._build_export_tab(export_tab)

        # Tab 2: Import
        import_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=16)
        notebook.add(import_tab, text="📥 Impor Data")
        self._build_import_tab(import_tab)

        # Tab 3: Template & Migration
        vnc_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=16)
        notebook.add(vnc_tab, text="📄 Migrasi & Template")
        self._build_vnc_tab(vnc_tab)

    def _build_export_tab(self, parent: ttk.Frame):
        ttk.Label(parent, text="Pilih Format Ekspor:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 4))
        self.export_fmt = tk.StringVar(value="json")
        ttk.Radiobutton(parent, text="JSON Backup Terenkripsi (Disarankan untuk backup lengkap)", variable=self.export_fmt, value="json", style="Surface.TRadiobutton").pack(anchor="w", pady=2)
        ttk.Radiobutton(parent, text="CSV Spreadsheet (Format tabel: Name, IP, Port, Group, Notes)", variable=self.export_fmt, value="csv", style="Surface.TRadiobutton").pack(anchor="w", pady=2)

        pw_frame = ttk.Frame(parent, style="Surface.TFrame")
        pw_frame.pack(fill="x", pady=(12, 12))
        ttk.Label(pw_frame, text="Master Password untuk enkripsi file backup (Opsional):", style="Surface.TLabel").pack(anchor="w", pady=(0, 2))
        self.export_pw_var = tk.StringVar()
        ttk.Entry(pw_frame, textvariable=self.export_pw_var, show="*").pack(fill="x")
        ttk.Label(pw_frame, text="* Jika diisi, data backup dapat dibuka di komputer lain dengan memasukkan password ini.", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(2, 0))

        ttk.Button(parent, text="💾 Ekspor Sekarang...", style="Primary.TButton", command=self._handle_export).pack(anchor="w", pady=(10, 0))

    def _build_import_tab(self, parent: ttk.Frame):
        ttk.Label(parent, text="Impor dari File Backup (JSON atau CSV):", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 4))

        pw_frame = ttk.Frame(parent, style="Surface.TFrame")
        pw_frame.pack(fill="x", pady=(8, 12))
        ttk.Label(pw_frame, text="Master Password (jika file backup JSON dienkripsi):", style="Surface.TLabel").pack(anchor="w", pady=(0, 2))
        self.import_pw_var = tk.StringVar()
        ttk.Entry(pw_frame, textvariable=self.import_pw_var, show="*").pack(fill="x")

        ttk.Button(parent, text="📂 Pilih File Backup (JSON / CSV)...", style="Primary.TButton", command=self._handle_import).pack(anchor="w", pady=(10, 0))

    def _build_vnc_tab(self, parent: ttk.Frame):
        ttk.Label(parent, text="Migrasi dari File Koneksi .vnc Lama:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        ttk.Label(parent, text="Impor otomatis file konfigurasi TightVNC / RealVNC (.vnc) yang sudah ada di PC Anda.", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Button(parent, text="📂 Impor File .vnc...", command=self._handle_import_vnc).pack(anchor="w", pady=(0, 16))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(parent, text="Template CSV:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        ttk.Label(parent, text="Download contoh file CSV untuk menginput puluhan data PC sekaligus via Excel.", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Button(parent, text="📥 Download Template CSV...", command=self._download_csv_template).pack(anchor="w")

    def _handle_export(self):
        fmt = self.export_fmt.get()
        pw = self.export_pw_var.get().strip() or None

        if fmt == "json":
            file_path = filedialog.asksaveasfilename(
                title="Simpan File Backup JSON",
                defaultextension=".json",
                filetypes=[("JSON Backup", "*.json")],
                parent=self
            )
            if not file_path:
                return
            try:
                count = DataExporter.export_to_json(self.db, file_path, master_password=pw)
                messagebox.showinfo("Sukses", f"Berhasil mengekspor {count} host ke file JSON.", parent=self)
                self.destroy()
            except Exception as e:
                messagebox.showerror("Gagal Ekspor", f"Terjadi kesalahan saat mengekspor: {e}", parent=self)
        else:
            file_path = filedialog.asksaveasfilename(
                title="Simpan File CSV",
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
                parent=self
            )
            if not file_path:
                return
            try:
                count = DataExporter.export_to_csv(self.db, file_path)
                messagebox.showinfo("Sukses", f"Berhasil mengekspor {count} host ke file CSV.", parent=self)
                self.destroy()
            except Exception as e:
                messagebox.showerror("Gagal Ekspor", f"Terjadi kesalahan saat mengekspor: {e}", parent=self)

    def _handle_import(self):
        file_path = filedialog.askopenfilename(
            title="Pilih File Backup",
            filetypes=[("Backup Files (JSON, CSV)", "*.json;*.csv"), ("JSON Files", "*.json"), ("CSV Files", "*.csv")],
            parent=self
        )
        if not file_path:
            return

        pw = self.import_pw_var.get().strip() or None
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".json":
                imported, skipped = DataExporter.import_from_json(self.db, file_path, master_password=pw)
            elif ext == ".csv":
                imported, skipped = DataExporter.import_from_csv(self.db, file_path)
            else:
                messagebox.showwarning("Format Tidak Dikenal", "Format file tidak didukung.", parent=self)
                return

            if self.on_data_changed:
                self.on_data_changed()

            messagebox.showinfo("Sukses", f"Berhasil mengimpor {imported} host (dilewati: {skipped}).", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Gagal Impor", f"Gagal mengimpor data: {e}", parent=self)

    def _handle_import_vnc(self):
        file_paths = filedialog.askopenfilenames(
            title="Pilih File .vnc",
            filetypes=[("VNC Files", "*.vnc")],
            parent=self
        )
        if not file_paths:
            return

        success = 0
        for fp in file_paths:
            h = DataExporter.import_from_vnc_file(self.db, fp)
            if h:
                success += 1

        if self.on_data_changed:
            self.on_data_changed()

        messagebox.showinfo("Sukses Migrasi", f"Berhasil mengimpor {success} file .vnc ke dalam address book.", parent=self)
        self.destroy()

    def _download_csv_template(self):
        file_path = filedialog.asksaveasfilename(
            title="Simpan Template CSV",
            initialfile="yutovnc_template.csv",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            parent=self
        )
        if not file_path:
            return

        sample_rows = [
            "Alias,IP,Port,Group,Password,ViewOnly,Fullscreen,Scaling,Notes",
            "Server IT Utama,192.168.1.10,5900,Server IT,rahasia123,0,0,auto,Server ruang server lantai 2",
            "PC Lab Komputer 01,192.168.10.101,5900,Lab Komputer,,0,0,auto,PC Siswa baris depan",
            "Kasir Toko 1,10.0.0.51,5900,Kasir / POS,kasirpass,0,0,auto,Mesin POS kasir utama"
        ]
        with open(file_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(sample_rows))

        messagebox.showinfo("Berhasil", f"Template CSV berhasil disimpan ke:\n{file_path}", parent=self)
