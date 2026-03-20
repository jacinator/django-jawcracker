from __future__ import annotations

from pathlib import Path

import polib
from django.conf import settings
from django.utils.translation import to_language

from jawcracker.models import Language, Translation


def get_po_paths() -> dict[str, Path]:
    """Discover django.po files from LOCALE_PATHS. Returns {locale_name: Path}."""
    return {
        z.parent.parent.name: z
        for x in settings.LOCALE_PATHS
        if (y := Path(x)).is_dir()
        for z in y.glob("*/LC_MESSAGES/django.po")
    }


def import_po_file(
    locale_name: str,
    po_path: Path,
    *,
    no_obsolete: bool = False,
) -> "Language":
    """Read a .po file and upsert Language + Translation records."""
    language_name = to_language(locale_name)
    language, _ = Language.objects.update_or_create(
        language_name=language_name,
        defaults={"locale_name": locale_name},
    )

    pf = polib.pofile(str(po_path))

    # Build Translation objects from all entries (including obsolete)
    all_entries = list(pf) + [e for e in pf.obsolete_entries() if e not in pf]
    translations = []
    imported_hashes = set()

    for order, entry in enumerate(all_entries):
        msgctxt = entry.msgctxt or ""
        msgid = entry.msgid
        h = Translation.compute_hash(msgctxt, msgid)
        imported_hashes.add(h)

        msgstr_plural = {str(k): v for k, v in entry.msgstr_plural.items()}
        flags = list(entry.flags)
        is_fuzzy = "fuzzy" in flags
        if entry.msgid_plural:
            is_translated = bool(any(v.strip() for v in msgstr_plural.values()))
        else:
            is_translated = bool(entry.msgstr.strip())

        translations.append(
            Translation(
                language=language,
                hash=h,
                order=order,
                msgid=msgid,
                msgid_plural=entry.msgid_plural or "",
                msgctxt=msgctxt,
                msgstr=entry.msgstr,
                msgstr_plural=msgstr_plural,
                flags=flags,
                occurrences=[list(occ) for occ in entry.occurrences],
                comment=entry.comment,
                tcomment=entry.tcomment,
                is_translated=is_translated,
                is_fuzzy=is_fuzzy,
                obsolete=entry.obsolete,
            )
        )

    if translations:
        Translation.objects.bulk_create(
            translations,
            update_conflicts=True,
            unique_fields=["language", "hash"],
            update_fields=[
                "order",
                "msgid",
                "msgid_plural",
                "msgctxt",
                "msgstr",
                "msgstr_plural",
                "flags",
                "occurrences",
                "comment",
                "tcomment",
                "is_translated",
                "is_fuzzy",
                "obsolete",
            ],
        )

    # Handle orphaned translations (in DB but not in .po file)
    orphaned = Translation.objects.filter(language=language).exclude(
        hash__in=imported_hashes
    )
    if no_obsolete:
        orphaned.delete()
    else:
        orphaned.update(obsolete=True)

    return language


def export_po_file(language: "Language", po_path: Path) -> Path:
    """Write a Language's translations to a .po file."""
    # Preserve existing metadata if the file already exists
    if po_path.exists():
        existing = polib.pofile(str(po_path))
        metadata = existing.metadata
    else:
        metadata = {
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "Language": language.language_name,
        }

    pf = polib.POFile()
    pf.metadata = metadata

    translations = Translation.objects.filter(
        language=language, obsolete=False
    ).order_by("order")

    for t in translations:
        entry = polib.POEntry(
            msgid=t.msgid,
            msgid_plural=t.msgid_plural or None,
            msgctxt=t.msgctxt or None,
            msgstr=t.msgstr,
            msgstr_plural={int(k): v for k, v in t.msgstr_plural.items()},
            flags=list(t.flags),
            occurrences=[tuple(occ) for occ in t.occurrences],
            comment=t.comment,
            tcomment=t.tcomment,
        )
        pf.append(entry)

    # Append obsolete entries
    obsolete_translations = Translation.objects.filter(
        language=language, obsolete=True
    ).order_by("order")

    for t in obsolete_translations:
        entry = polib.POEntry(
            msgid=t.msgid,
            msgid_plural=t.msgid_plural or None,
            msgctxt=t.msgctxt or None,
            msgstr=t.msgstr,
            msgstr_plural={int(k): v for k, v in t.msgstr_plural.items()},
            flags=list(t.flags),
            occurrences=[tuple(occ) for occ in t.occurrences],
            comment=t.comment,
            tcomment=t.tcomment,
            obsolete=True,
        )
        pf.append(entry)

    po_path.parent.mkdir(parents=True, exist_ok=True)
    pf.save(str(po_path))
    return po_path
