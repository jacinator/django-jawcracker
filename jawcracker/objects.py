from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from django.conf import settings
from django.core.cache import cache
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
    pofile: POFile = field(compare=False, init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pofile", SimpleLazyObject(lambda: pofile(self.path)))

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
        return len(self.pofile)

    @property
    def translated(self) -> int:
        return len(self.pofile.translated_entries())

    @property
    def fuzzy(self) -> int:
        return len(self.pofile.fuzzy_entries())

    @property
    def untranslated(self) -> int:
        return len(self.pofile.untranslated_entries())

    @property
    def percent(self) -> int:
        return self.pofile.percent_translated()


@dataclass(frozen=True, slots=True)
class LanguageManager(Mapping[str, Language]):
    _paths: dict[str, Path]

    @staticmethod
    def get_paths() -> dict[str, Path]:
        return {
            z.parent.parent.name: z
            for x in settings.LOCALE_PATHS
            if (y := Path(x)).is_dir()
            for z in y.glob("*/LC_MESSAGES/django.po")
        }

    def __init__(self) -> None:
        object.__setattr__(self, "_paths", SimpleLazyObject(LanguageManager.get_paths))

    def __getitem__(self, language_name: str) -> Language:
        locale_name = to_locale(language_name)
        return Language(language_name, locale_name, self._paths[locale_name])

    def __iter__(self) -> Iterator[str]:
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


Index: TypeAlias = dict[str, tuple[int, str | None, str | None]]


@dataclass(frozen=True, slots=True)
class TranslationManager(Mapping[str, Translation]):
    language: Language
    pofile: POFile = field(compare=False, init=False, repr=False)
    _index: Index = field(compare=False, init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pofile", self.language.pofile)
        object.__setattr__(self, "_index", SimpleLazyObject(self._get_index))

    def __getitem__(self, hash_: str) -> Translation:
        index, _, _ = self._index[hash_]
        return Translation(self.language, self.pofile[index])

    def __iter__(self) -> Iterator[str]:
        yield from self._index

    def __len__(self) -> int:
        return len(self._index)

    def _get_index(self) -> Index:
        def cache_value() -> Index:
            hashes = [Translation.hash(entry) for entry in self.pofile]
            n = len(hashes)
            return {
                h: (i, hashes[(i + 1) % n], hashes[(i - 1 + n) % n])
                for i, h in enumerate(hashes)
            }

        mtime: float = self.language.path.stat().st_mtime
        cache_key: str = f"jawcracker:index:{self.language.path}:{mtime}"

        return cache.get_or_set(cache_key, cache_value)

    def get_next(self, hash_: str) -> str | None:
        with suppress(KeyError, TypeError):
            return self._index[hash_][1]

    def get_previous(self, hash_: str) -> str | None:
        with suppress(KeyError, TypeError):
            return self._index[hash_][2]
