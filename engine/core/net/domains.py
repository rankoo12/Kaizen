from __future__ import annotations


def normalize_registrable_domain(host: str | None) -> str | None:
    """Best-effort registrable domain (eTLD+1) without external deps.

    - Returns lowercased host when parsing fails or host is an IP/localhost.
    - Handles common multi-part TLDs heuristically (e.g., co.uk, com.au).
    - Not a full public suffix implementation; safe, deterministic fallback.
    """
    if not host:
        return None
    h = host.strip().lower()
    if not h:
        return None
    # Short-circuit for localhost and IPs
    if h == "localhost" or all(ch.isdigit() or ch == "." for ch in h):
        return h
    parts = h.split(".")
    if len(parts) <= 2:
        return h
    # Heuristic for common second-level TLD buckets
    sld_buckets = {"co", "com", "org", "net", "gov", "edu"}
    tld = parts[-1]
    sld = parts[-2]
    if sld in sld_buckets and len(parts) >= 3:
        # example.co.uk -> example.co.uk ; app.example.co.uk -> example.co.uk
        return ".".join(parts[-3:])
    # Default to last two labels
    return ".".join(parts[-2:])
