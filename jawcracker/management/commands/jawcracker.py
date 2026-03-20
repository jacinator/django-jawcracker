from enum import StrEnum
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandParser
from django.utils.translation import to_language, to_locale
from polib import POEntry, POFile, pofile

from jawcracker.models import Language, Translation
from jawcracker.utils import get_po_paths


class Action(StrEnum):
    COMPILEMESSAGES = "compilemessages"
    MAKEMESSAGES = "makemessages"


class Command(BaseCommand):
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=list(Action), type=Action)
        parser.add_argument("--all", "-a", action="store_true")
        parser.add_argument("--language", "-l", action="append", dest="locales")

    def handle(self, action: Action, **options: Any) -> str | None:
        return getattr(self, action)(**options)

    def compilemessages(self, locales: list[str], **options: Any) -> str | None:
        languages = Language.objects.all()
        if locales:
            languages = languages.filter(locale_name__in=locales)

        for lang_obj in languages:
            path = self._find_po_path(lang_obj)
            if not path:
                self.stderr.write(
                    self.style.WARNING(
                        f"No locale path found for {lang_obj.language_name}, skipping"
                    )
                )
                continue

            self.stdout.write(f"Exporting {lang_obj.language_name} to {path}...")

            if path.exists():
                po = pofile(str(path))
                # Clear existing entries; we rebuild from DB
                del po[:]
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                po = POFile()
                po.metadata = {
                    "Content-Type": "text/plain; charset=UTF-8",
                    "Content-Transfer-Encoding": "8bit",
                }

            translations = lang_obj.translations.order_by("order")

            for trans in translations:
                entry = POEntry(
                    msgid=trans.msgid,
                    msgctxt=trans.msgctxt or None,
                    msgstr=trans.msgstr,
                    msgid_plural=trans.msgid_plural or None,
                    comment=trans.comment,
                    tcomment=trans.tcomment,
                    occurrences=[tuple(occ) for occ in trans.occurrences],
                    flags=list(trans.flags),
                    obsolete=trans.obsolete,
                )
                if trans.msgid_plural:
                    entry.msgstr_plural = {
                        int(k): v for k, v in trans.msgstr_plural.items()
                    }
                po.append(entry)

            po.save(str(path))

            mo_path = str(path).replace(".po", ".mo")
            po.save_as_mofile(mo_path)

            self.stdout.write(
                self.style.SUCCESS(
                    f"  {lang_obj.language_name}: saved {path} and {mo_path}"
                )
            )

    def makemessages(self, all: bool, locales: list[str], **options: Any) -> str | None:
        call_command("makemessages", all=all, locale=locales)
        paths = get_po_paths()

        for locale_name, path in paths.items():
            if not locales or locale_name in locales:
                continue

            language_name = to_language(locale_name)
            self.stdout.write(f"Importing {language_name} from {path}...")
            po = pofile(str(path))

            lang_obj, _ = Language.objects.get_or_create(
                language_name=language_name,
                defaults={"locale_name": locale_name},
            )

            seen_hashes = set()
            created_count = 0
            updated_count = 0

            for i, entry in enumerate(po):
                h = Translation.compute_hash(entry.msgctxt or "", entry.msgid)
                seen_hashes.add(h)

                defaults = {
                    "order": i,
                    "msgid": entry.msgid,
                    "msgid_plural": entry.msgid_plural or "",
                    "msgctxt": entry.msgctxt or "",
                    "msgstr": entry.msgstr or "",
                    "msgstr_plural": {
                        str(k): v for k, v in entry.msgstr_plural.items()
                    },
                    "flags": list(entry.flags),
                    "occurrences": [list(occ) for occ in entry.occurrences],
                    "comment": entry.comment or "",
                    "tcomment": entry.tcomment or "",
                    "obsolete": entry.obsolete,
                }

                _, was_created = Translation.objects.update_or_create(
                    language=lang_obj,
                    hash=h,
                    defaults=defaults,
                )
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1

            deleted_count, _ = (
                Translation.objects.filter(language=lang_obj)
                .exclude(hash__in=seen_hashes)
                .delete()
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  {language_name}: {created_count} created, "
                    f"{updated_count} updated, {deleted_count} deleted"
                )
            )

    @staticmethod
    def _find_po_path(lang_obj: Language) -> Path | None:
        locale_name = to_locale(lang_obj.language_name)
        for locale_path in settings.LOCALE_PATHS:
            candidate = Path(locale_path) / locale_name / "LC_MESSAGES" / "django.po"
            if candidate.exists() or Path(locale_path).is_dir():
                return candidate
        return None
