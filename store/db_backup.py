# invent_app/app/store/db_backup.py
import os
import shutil
from datetime import datetime
from django.conf import settings

# Backups folder will be created at: <BASE_DIR>/backups
BACKUP_DIR = os.path.join(settings.BASE_DIR, "backups")
MAX_BACKUPS = 3


def create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # sort by creation time (oldest first)
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sqlite3")],
        key=lambda x: os.path.getctime(os.path.join(BACKUP_DIR, x))
    )

    # if we already have MAX_BACKUPS, delete the oldest
    if len(backups) >= MAX_BACKUPS:
        os.remove(os.path.join(BACKUP_DIR, backups[0]))

    name = f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.sqlite3"
    dst = os.path.join(BACKUP_DIR, name)

    # copy database file (preserves metadata)
    shutil.copy2(settings.DATABASES["default"]["NAME"], dst)
    return name


def list_backups():
    if not os.path.exists(BACKUP_DIR):
        return []
    # return newest-first
    return sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".sqlite3")], reverse=True)


def restore_backup(filename):
    src = os.path.join(BACKUP_DIR, filename)
    dst = settings.DATABASES["default"]["NAME"]

    if not os.path.exists(src):
        raise FileNotFoundError("Backup file not found: %s" % filename)

    # Overwrite current DB with selected backup
    shutil.copy2(src, dst)
