#!/usr/bin/env python3
import sys
from pathlib import Path

# Folders to scan (templates under apps and top-level 'templates')
scan_roots = [
    Path('accounts/templates'),
    Path('store/templates'),
    Path('transactions/templates'),
    Path('invoice/templates'),
    Path('templates'),
]

# Find all html / txt / template files
exts = {'.html', '.htm', '.txt', '.tmpl', '.django'}
candidates = []
for root in scan_roots:
    if not root.exists():
        continue
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in exts:
            candidates.append(p)

if not candidates:
    print("No template files found in expected locations. You can edit scan_roots in the script.")
    sys.exit(0)

def try_decode(data):
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return enc, data.decode(enc)
        except Exception:
            continue
    # last resort: decode with replacement so file is readable
    return 'utf-8-replace', data.decode('utf-8', errors='replace')

fixed = 0
for p in candidates:
    try:
        raw = p.read_bytes()
    except Exception as e:
        print(f"[SKIP] cannot read {p}: {e}")
        continue

    enc, text = try_decode(raw)
    if enc == 'utf-8':
        # already fine
        continue

    # make backup
    bak = p.with_suffix(p.suffix + '.bak')
    if not bak.exists():
        p.replace(bak)  # move original to .bak
        # write UTF-8 text to original path (which is now free)
        p.write_text(text, encoding='utf-8')
        print(f"[CONVERTED] {p}  (decoded as {enc}, backup -> {bak})")
        fixed += 1
    else:
        # backup exists, don't overwrite it; write to a temporary file then replace
        tmp = p.with_suffix(p.suffix + '.utf8tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(p)
        print(f"[REPLACED] {p} (decoded as {enc}, existing backup left at {bak})")
        fixed += 1

print(f"Done. Files converted: {fixed}")
print("If you still see UnicodeDecodeError, check the stack trace to find the exact template path.")
