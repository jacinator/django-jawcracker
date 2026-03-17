from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse_lazy
from django.utils.functional import SimpleLazyObject
from django.utils.translation import get_language_info, to_language, to_locale
from polib import pofile

if TYPE_CHECKING:
    from collections.abc import Iterator

    from polib import POEntry, POFile


@dataclass(frozen=True, slots=True)
class Language:
    language_name: str  # en-us
    locale_name: str  # en_US
    path: Path  # local/en_US/LC_MESSAGES/django.po
    _pofile: POFile = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_pofile", SimpleLazyObject(lambda: pofile(self.path)))

    def __str__(self) -> str:  # English
        try:
            return get_language_info(self.language_name)["name_local"]
        except KeyError:
            return self.language_name

    def __contains__(self, value: str) -> bool:
        query: str = value.lower()
        return (
            query in str(self).lower()
            or query in self.language_name
            or query in self.locale_name
        )

    def get_absolute_url(self) -> str:
        return reverse_lazy(
            "jawcracker-language-detail",
            kwargs={"language_id": self.language_name},
        )

    @property
    def total(self) -> int:
        return len(self._pofile)

    @property
    def translated(self) -> int:
        return len(self._pofile.translated_entries())

    @property
    def fuzzy(self) -> int:
        return len(self._pofile.fuzzy_entries())

    @property
    def untranslated(self) -> int:
        return len(self._pofile.untranslated_entries())

    @property
    def percent(self) -> int:
        return self._pofile.percent_translated()


def _default_paths() -> dict[str, Path]:
    return SimpleLazyObject(
        lambda: {
            z.parent.parent.name: z
            for x in settings.LOCALE_PATHS
            if (y := Path(x)).is_dir()
            for z in y.glob("*/LC_MESSAGES/django.po")
        }
    )


@dataclass(frozen=True, slots=True)
class LanguageManager(Mapping[str, Language]):
    _paths: dict[str, Path] = field(default_factory=_default_paths, init=False)

    def __getitem__(self, language_name: str) -> Language:
        locale_name = to_locale(language_name)
        return Language(language_name, locale_name, self._paths[locale_name])

    def __iter__(self) -> Iterator[Language]:
        return (to_language(x) for x in self._paths)

    def __len__(self) -> int:
        return len(self._paths)


@dataclass(frozen=True, slots=True)
class Translation:
    language: Language
    entry: POEntry

    @staticmethod
    def hash(entry: POEntry) -> str:
        key = f"{entry.msgctxt or ''}\x00{entry.msgid}"
        return sha256(key.encode()).hexdigest()

    def __contains__(self, value: str) -> bool:
        query: str = value.lower()
        entry: POEntry = self.entry
        return (
            query in entry.msgid.lower()
            or query in entry.msgid_plural.lower()
            or query in entry.msgstr.lower()
            or any(query in y for y in entry.msgstr_plural.values())
        )

    def get_absolute_url(self) -> str:
        return reverse_lazy(
            "jawcracker-translation-detail",
            kwargs={
                "language_id": self.language.language_name,
                "translation_id": Translation.hash(self.entry),
            },
        )


@dataclass(frozen=True, slots=True)
class TranslationManager(Mapping[str, Translation]):
    language: Language
    pofile: POFile

    def __init__(self, language: Language) -> None:
        object.__setattr__(self, "language", language)
        object.__setattr__(
            self, "pofile", SimpleLazyObject(lambda: pofile(language.path))
        )

    def __iter__(self) -> Iterator[Translation]:
        for entry in self.pofile:
            yield Translation.hash(entry)

    def __getitem__(self, translation_hash: str) -> Translation:
        try:
            return next(
                Translation(self.language, x)
                for x in self.pofile
                if Translation.hash(x) == translation_hash
            )
        except StopIteration as e:
            raise KeyError from e

    def __len__(self) -> int:
        return len(self.pofile)

    def get_next(self, translation_hash: str) -> str | None:
        for a, b in pairwise(self.pofile):
            if Translation.hash(a) == translation_hash:
                return Translation.hash(b)

    def get_previous(self, translation_hash: str) -> str | None:
        for a, b in pairwise(self.pofile):
            if Translation.hash(b) == translation_hash:
                return Translation.hash(a)
