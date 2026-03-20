from enum import StrEnum
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandParser
from django.utils.translation import to_locale
import polib

from jawcracker.models import Language
from jawcracker.utils import export_po_file, get_po_paths, import_po_file


class Action(StrEnum):
    COMPILEMESSAGES = "compilemessages"
    MAKEMESSAGES = "makemessages"


class Command(BaseCommand):
    help = "Manage jawcracker translations"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=list(Action), type=Action)
        parser.add_argument(
            "--locale",
            "-l",
            action="append",
            default=[],
            help="Locale(s) to process. Can be used multiple times.",
        )
        parser.add_argument(
            "--all",
            "-a",
            action="store_true",
            dest="process_all",
            help="Process all existing locales.",
        )
        parser.add_argument(
            "--no-obsolete",
            action="store_true",
            help="Delete (rather than mark obsolete) translations no longer in source.",
        )
        parser.add_argument(
            "--use-msgfmt",
            action="store_true",
            help="Use msgfmt instead of polib for .mo compilation.",
        )

    def handle(self, action: Action, **options: Any) -> str | None:
        return getattr(self, action)(**options)

    def makemessages(
        self,
        locale: list[str],
        process_all: bool,
        no_obsolete: bool,
        verbosity: int,
        **options: Any,
    ) -> None:
        # Phase 1: Run Django's makemessages to create/update .po files on disk.
        mm_kwargs = {"verbosity": verbosity}
        if locale:
            mm_kwargs["locale"] = locale
        elif process_all:
            mm_kwargs["all"] = True
        else:
            mm_kwargs["all"] = True

        call_command("makemessages", **mm_kwargs)

        # Phase 2: Import .po files into the database.
        po_paths = get_po_paths()

        if locale:
            requested = {to_locale(loc) for loc in locale}
            po_paths = {k: v for k, v in po_paths.items() if k in requested}

        for locale_name, po_path in po_paths.items():
            if verbosity > 0:
                self.stdout.write(f"Importing {po_path} ...")
            import_po_file(locale_name, po_path, no_obsolete=no_obsolete)

        if verbosity > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Imported {len(po_paths)} locale(s) into the database."
                )
            )

    def compilemessages(
        self, locale: list[str], use_msgfmt: bool, verbosity: int, **options: Any
    ) -> None:
        po_paths = get_po_paths()
        languages = Language.objects.all()

        if locale:
            requested = {to_locale(loc) for loc in locale}
            languages = languages.filter(locale_name__in=requested)

        exported_paths = []
        for lang in languages:
            po_path = po_paths.get(lang.locale_name)
            if po_path is None:
                if not settings.LOCALE_PATHS:
                    self.stderr.write(
                        f"No LOCALE_PATHS configured, skipping {lang.locale_name}"
                    )
                    continue
                base = Path(settings.LOCALE_PATHS[0])
                po_path = base / lang.locale_name / "LC_MESSAGES" / "django.po"

            if verbosity > 0:
                self.stdout.write(f"Exporting {lang.language_name} to {po_path} ...")
            export_po_file(lang, po_path)
            exported_paths.append(po_path)

        # Compile .po → .mo
        if use_msgfmt:
            cm_kwargs = {"verbosity": verbosity}
            if locale:
                cm_kwargs["locale"] = locale
            call_command("compilemessages", **cm_kwargs)
        else:
            for po_path in exported_paths:
                mo_path = po_path.with_suffix(".mo")
                if verbosity > 0:
                    self.stdout.write(f"Compiling {po_path} -> {mo_path} ...")
                pf = polib.pofile(str(po_path))
                pf.save_as_mofile(str(mo_path))

        if verbosity > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Compiled {len(exported_paths)} .po file(s) to .mo."
                )
            )
