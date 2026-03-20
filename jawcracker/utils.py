from __future__ import annotations

from pathlib import Path

from django.conf import settings


def get_po_paths() -> dict[str, Path]:
    """Discover django.po files from LOCALE_PATHS. Returns {locale_name: Path}."""
    return {
        z.parent.parent.name: z
        for x in settings.LOCALE_PATHS
        if (y := Path(x)).is_dir()
        for z in y.glob("*/LC_MESSAGES/django.po")
    }
