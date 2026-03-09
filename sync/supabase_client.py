"""
supabase_client.py
──────────────────
Single place that owns the HTTP connection to Supabase.
Uses plain requests (no supabase-py) to avoid HTTP/2 disconnects.

All other sync code imports from here — nothing else should
build headers or URLs directly.
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger("sync")

PAGE_SIZE  = 1000   # PostgREST default; we page with Range headers
BATCH_SIZE = 200    # rows per POST batch (upsert)
TIMEOUT    = 30     # seconds


def is_enabled() -> bool:
    return bool(getattr(settings, "SUPABASE_SYNC_ENABLED", False))


def _base_headers(extra: dict | None = None) -> dict:
    key = settings.SUPABASE_KEY
    h = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }
    if extra:
        h.update(extra)
    return h


def table_url(table: str) -> str:
    return f"{settings.SUPABASE_URL}/rest/v1/{table}"


# ── low-level primitives ───────────────────────────────────────────────────────

def post_rows(table: str, rows: list) -> bool:
    """POST (upsert) a list of rows. Returns True on HTTP 200/201."""
    try:
        r = requests.post(
            table_url(table), json=rows,
            headers=_base_headers(), timeout=TIMEOUT,
        )
        if r.status_code in (200, 201):
            return True
        logger.warning("Supabase POST %s → %s: %s", table, r.status_code, r.text[:300])
        return False
    except Exception as exc:
        logger.warning("Supabase POST %s exception: %s", table, exc)
        return False


def delete_row(table: str, pk) -> bool:
    """DELETE a single row by its id. Returns True on HTTP 200/204."""
    try:
        r = requests.delete(
            table_url(table),
            headers=_base_headers(),
            params={"id": f"eq.{pk}"},
            timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception as exc:
        logger.warning("Supabase DELETE %s id=%s: %s", table, pk, exc)
        return False


def fetch_all_rows(table: str) -> list[dict]:
    """Fetch every row from a Supabase table, paging with Range headers."""
    all_rows: list[dict] = []
    start = 0
    while True:
        end = start + PAGE_SIZE - 1
        try:
            r = requests.get(
                table_url(table),
                headers=_base_headers({"Range": f"{start}-{end}"}),
                params={"select": "*"},
                timeout=TIMEOUT,
            )
        except Exception as exc:
            logger.warning("Supabase GET %s exception: %s", table, exc)
            break

        if r.status_code not in (200, 206):
            logger.warning("Supabase GET %s → %s: %s", table, r.status_code, r.text[:200])
            break

        chunk = r.json()
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return all_rows


# ── batch upsert with per-row fallback ────────────────────────────────────────

def batch_upsert(table: str, rows: list) -> int:
    """
    Upsert rows in chunks of BATCH_SIZE.
    If a chunk fails, retries each row individually.
    Returns the count of successfully upserted rows.
    """
    if not rows:
        return 0
    success = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i: i + BATCH_SIZE]
        if post_rows(table, chunk):
            success += len(chunk)
        else:
            for row in chunk:
                if post_rows(table, [row]):
                    success += 1
                else:
                    logger.warning("Row failed permanently – %s id=%s", table, row.get("id"))
    return success


def nuke_table(table: str) -> bool:
    """
    DELETE all rows from a Supabase table.
    Used by the wipe-and-resync command.
    PostgREST requires at least one filter; id=gte.0 matches every positive-int PK.
    """
    try:
        r = requests.delete(
            table_url(table),
            headers=_base_headers(),
            params={"id": "gte.0"},
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 204):
            return True
        # Some tables have non-integer PKs — fall back to neq trick
        r2 = requests.delete(
            table_url(table),
            headers=_base_headers(),
            params={"id": "neq.-1"},
            timeout=TIMEOUT,
        )
        return r2.status_code in (200, 204)
    except Exception as exc:
        logger.warning("Supabase NUKE %s: %s", table, exc)
        return False
