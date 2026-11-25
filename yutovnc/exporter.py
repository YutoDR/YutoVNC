"""Data import, export, and migration module for YutoVNC.

Supports:
- JSON Export/Import with optional Master Password encryption or DPAPI
- CSV Export/Import for bulk host configuration
- Legacy .vnc connection file migration (TightVNC / RealVNC)
"""

import os
import json
import csv
import configparser
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from yutovnc.models import Host
from yutovnc.database import Database
from yutovnc.security import (
    encrypt_password_dpapi,
    decrypt_password_dpapi,
    encrypt_with_master_password,
    decrypt_with_master_password
)

class DataExporter:
    @staticmethod
    def export_to_json(
        db: Database,
        file_path: str,
        master_password: Optional[str] = None
    ) -> int:
        """Export all hosts and groups to a JSON file.
        If master_password is provided, passwords are encrypted with master password (portable).
        Otherwise, passwords are exported in DPAPI encrypted format.
        """
        hosts = db.get_all_hosts()
        groups = db.get_groups()

        host_dicts = []
        for h in hosts:
            d = h.to_dict()
            # If master password provided, decrypt DPAPI and re-encrypt with master password
            if master_password and h.password_enc:
                try:
                    plain = decrypt_password_dpapi(h.password_enc)
                    d["password_portable"] = plain
                except Exception:
                    d["password_portable"] = ""
            d.pop("id", None)  # let import assign new IDs
            host_dicts.append(d)

        payload = {
            "app": "YutoVNC",
            "version": "1.0",
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "groups": groups,
            "hosts": host_dicts
        }

        raw_json = json.dumps(payload, indent=2, ensure_ascii=False)

        if master_password:
            # Package the entire JSON inside master password encryption
            enc_container = {
                "app": "YutoVNC",
                "encrypted": True,
                "data": encrypt_with_master_password(raw_json, master_password)
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(enc_container, f, indent=2)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(raw_json)

        return len(hosts)

    @staticmethod
    def import_from_json(
        db: Database,
        file_path: str,
        master_password: Optional[str] = None
    ) -> Tuple[int, int]:
        """Import hosts and groups from JSON. Returns (imported_count, skipped_count)."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("encrypted"):
            if not master_password:
                raise ValueError("This backup file is encrypted with a master password.")
            decrypted_str = decrypt_with_master_password(data["data"], master_password)
            data = json.loads(decrypted_str)

        groups = data.get("groups", [])
        for g in groups:
            db.add_group(g)

        imported = 0
        skipped = 0
        existing_hosts = db.get_all_hosts()
        existing_signatures = {(h.ip, h.port) for h in existing_hosts}

        for item in data.get("hosts", []):
            ip = item.get("ip", "").strip()
            port = int(item.get("port", 5900))
            if not ip:
                skipped += 1
                continue

            # Determine password
            enc_pw = ""
            if "password_portable" in item and item["password_portable"]:
                enc_pw = encrypt_password_dpapi(item["password_portable"])
            elif item.get("password_enc"):
                enc_pw = item["password_enc"]

            host = Host(
                alias=item.get("alias", f"Host {ip}"),
                ip=ip,
                port=port,
                group=item.get("group", "Default"),
                password_enc=enc_pw,
                view_only=bool(item.get("view_only", False)),
                fullscreen=bool(item.get("fullscreen", False)),
                scaling=item.get("scaling", "auto"),
                notes=item.get("notes", ""),
                is_favorite=bool(item.get("is_favorite", False))
            )

            db.add_host(host)
            imported += 1

        return imported, skipped

    @staticmethod
    def export_to_csv(db: Database, file_path: str) -> int:
        """Export hosts to CSV format (Name, IP, Port, Group, Notes)."""
        hosts = db.get_all_hosts()
        fieldnames = ["Alias", "IP", "Port", "Group", "ViewOnly", "Fullscreen", "Scaling", "Notes"]

        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for h in hosts:
                writer.writerow({
                    "Alias": h.alias,
                    "IP": h.ip,
                    "Port": h.port,
                    "Group": h.group,
                    "ViewOnly": "1" if h.view_only else "0",
                    "Fullscreen": "1" if h.fullscreen else "0",
                    "Scaling": h.scaling,
                    "Notes": h.notes
                })
        return len(hosts)

    @staticmethod
    def import_from_csv(db: Database, file_path: str, default_password: str = "") -> Tuple[int, int]:
        """Import hosts from CSV file."""
        imported = 0
        skipped = 0
        enc_default = encrypt_password_dpapi(default_password) if default_password else ""

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                alias = (row.get("Alias") or row.get("Name") or "").strip()
                ip = (row.get("IP") or row.get("IP Address") or "").strip()
                if not ip:
                    skipped += 1
                    continue

                try:
                    port = int(row.get("Port", 5900))
                except ValueError:
                    port = 5900

                group = (row.get("Group") or row.get("Category") or "Default").strip()
                view_only = row.get("ViewOnly", "0").strip().lower() in ("1", "true", "yes")
                fullscreen = row.get("Fullscreen", "0").strip().lower() in ("1", "true", "yes")
                scaling = (row.get("Scaling") or "auto").strip()
                notes = (row.get("Notes") or "").strip()

                raw_pwd = row.get("Password", "").strip()
                password_enc = encrypt_password_dpapi(raw_pwd) if raw_pwd else enc_default

                db.add_group(group)
                host = Host(
                    alias=alias or f"Host {ip}",
                    ip=ip,
                    port=port,
                    group=group,
                    password_enc=password_enc,
                    view_only=view_only,
                    fullscreen=fullscreen,
                    scaling=scaling,
                    notes=notes
                )
                db.add_host(host)
                imported += 1

        return imported, skipped

    @staticmethod
    def import_from_vnc_file(db: Database, file_path: str) -> Optional[Host]:
        """Import a single .vnc legacy connection file."""
        parser = configparser.ConfigParser()
        try:
            parser.read(file_path, encoding="utf-8")
        except Exception:
            parser.read(file_path, encoding="latin1")

        host_ip = ""
        port = 5900
        view_only = False
        fullscreen = False

        # TightVNC format
        if parser.has_section("Connection"):
            host_ip = parser.get("Connection", "Host", fallback="")
            port = parser.getint("Connection", "Port", fallback=5900)
        elif parser.has_section("options"):
            # RealVNC format
            host_str = parser.get("options", "relative_host", fallback="") or parser.get("options", "host", fallback="")
            if ":" in host_str:
                parts = host_str.split(":")
                host_ip = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    port = 5900
            else:
                host_ip = host_str

        if not host_ip:
            # Fallback: parse raw lines
            with open(file_path, "r", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("host="):
                        host_ip = line.split("=", 1)[1].strip()
                    elif line.lower().startswith("port="):
                        try:
                            port = int(line.split("=", 1)[1].strip())
                        except ValueError:
                            pass

        if not host_ip:
            return None

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        alias = base_name.replace("_", " ").replace("-", " ")

        host = Host(
            alias=alias,
            ip=host_ip,
            port=port,
            group="Imported .vnc",
            view_only=view_only,
            fullscreen=fullscreen,
            notes=f"Migrated from {os.path.basename(file_path)}"
        )
        db.add_group("Imported .vnc")
        db.add_host(host)
        return host
