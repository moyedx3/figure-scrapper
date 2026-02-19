---
title: Duplicated Logic in Utility Scripts Causes Silent Failures
date: 2026-02-19
category: logic-errors
tags: [code-duplication, dry-violation, utility-scripts, backfill]
module: [backfill_jan_codes, page_fetcher]
symptoms:
  - Utility script silently returns 0 results despite fix being applied
  - Script has outdated filter/skip that was already removed in main code
  - Fix applied to one file but duplicate logic in another file not updated
severity: medium
---

# Duplicated Logic in Utility Scripts Causes Silent Failures

## Symptom

After adding comicsart JAN code support to `extraction/page_fetcher.py`, the
`backfill_jan_codes.py` script still returned 0 results for comicsart.
This happened **twice** in the same session:

1. Script still had `AND site != 'comicsart'` in its SQL query
2. Script had its own `_fetch_jan()` function that only parsed `<th>/<td>` tables,
   missing the `div.disnoul_left` pattern we just added to `page_fetcher.py`

## Root Cause

**Code duplication.** The backfill script was written with its own copy of the
parsing logic (for parallelization with per-site sessions) instead of reusing
`fetch_product_detail()` from `page_fetcher.py`. When the source of truth was
updated, the duplicate was not.

This is a classic DRY violation. The duplication happened because:
- The backfill script needed per-site `requests.Session` objects for parallel fetching
- Instead of adapting `fetch_product_detail()` to accept a session parameter, a
  separate `_fetch_jan()` was written that duplicated the parsing logic
- The hardcoded `site != 'comicsart'` filter was copied from the original
  sequential script without thinking about why it existed

## Prevention Rules

### 1. Never duplicate parsing/extraction logic

If a utility script needs the same parsing as the main code, **call the main
code's function**. If the function signature doesn't fit (e.g., needs a custom
session), refactor the function to accept optional parameters rather than copying it.

**Bad:**
```python
# backfill_jan_codes.py — has its own parsing copy
def _fetch_jan(url, site, session):
    # ... duplicated table parsing ...
    return jan
```

**Good:**
```python
# backfill_jan_codes.py — reuses the source of truth
from extraction.page_fetcher import fetch_product_detail
specs = fetch_product_detail(url, site)
jan = specs.get("jan_code") if specs else None
```

### 2. When updating a function, grep for duplicates

Before considering a fix "done", always search for other copies:
```bash
grep -r "the_function_or_pattern" --include="*.py"
```

### 3. When removing a skip/filter, grep for all occurrences

```bash
grep -r "comicsart" --include="*.py"
```

If you remove `site == "comicsart"` in one file, check ALL files.

### 4. Always test the actual script, not just the library function

Testing `fetch_product_detail()` in isolation passed, but the script that
users actually run (`backfill_jan_codes.py`) was never tested end-to-end
before pushing. Always test the entry point users will invoke.

## Checklist: Writing Utility/Migration Scripts

- [ ] Does this script duplicate any logic from the main codebase? If yes, refactor to reuse.
- [ ] Does this script have hardcoded filters? Are they still valid?
- [ ] Run the script locally with a small sample before pushing.
- [ ] `grep` for any filter terms (site names, column names) across all `.py` files.
