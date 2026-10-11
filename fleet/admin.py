"""Local administration; no credentials are printed or stored in source files."""
import argparse
import getpass
import os
import sqlite3
from pathlib import Path

from fleet.auth import hash_password
from fleet.db import connect, migrate, now


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("password", help="Místně nastavit nebo změnit přístupové heslo")
    backup = sub.add_parser("backup", help="Konzistentní soukromá záloha SQLite")
    backup.add_argument("path", type=Path)
    args = parser.parse_args()
    migrate()
    if args.command == "password":
        password = getpass.getpass("Nové heslo (alespoň 12 znaků): ")
        confirmation = getpass.getpass("Zopakujte heslo: ")
        if password != confirmation or not 12 <= len(password) <= 256:
            raise SystemExit("Hesla musí být stejná a mít 12–256 znaků.")
        with connect() as con, con:
            con.execute("INSERT INTO users VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash", (hash_password(password), now()))
            con.execute("DELETE FROM sessions")
        print("Heslo změněno, dosavadní relace odhlášeny.")
    elif args.command == "backup":
        path = args.path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with connect() as con, sqlite3.connect(path) as target:
                con.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Kontrola zálohy selhala")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        print(f"Soukromá záloha ověřena: {path}")


if __name__ == "__main__":
    main()
