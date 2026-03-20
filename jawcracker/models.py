from __future__ import annotations

from hashlib import sha256

from django.db import models
from django.urls import reverse
from django.utils.translation import get_language_info


class Language(models.Model):
    language_name = models.SlugField(max_length=20, unique=True)
    locale_name = models.CharField(max_length=20)

    class Meta:
        ordering = ["language_name"]

    def __str__(self) -> str:
        try:
            return get_language_info(self.language_name)["name_local"]
        except KeyError:
            return self.language_name

    def get_absolute_url(self) -> str:
        return reverse(
            "jawcracker-language-detail",
            kwargs={"language_id": self.language_name},
        )

    @property
    def total(self) -> int:
        return self.translations.count()

    @property
    def translated(self) -> int:
        return self.translations.filter(is_translated=True, is_fuzzy=False).count()

    @property
    def fuzzy(self) -> int:
        return self.translations.filter(is_fuzzy=True).count()

    @property
    def untranslated(self) -> int:
        return self.translations.filter(is_translated=False).count()

    @property
    def percent(self) -> int:
        total = self.total
        if total == 0:
            return 100
        return int(100 * self.translated / total)


class Translation(models.Model):
    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    hash = models.CharField(max_length=64, db_index=True)
    order = models.PositiveIntegerField(default=0)

    # Source fields (not editable in UI)
    msgid = models.TextField()
    msgid_plural = models.TextField(blank=True, default="")
    msgctxt = models.TextField(blank=True, default="")

    # Translation fields (editable in UI)
    msgstr = models.TextField(blank=True, default="")
    msgstr_plural = models.JSONField(blank=True, default=dict)

    # Metadata for .po round-tripping
    flags = models.JSONField(blank=True, default=list)
    occurrences = models.JSONField(blank=True, default=list)
    comment = models.TextField(blank=True, default="")
    tcomment = models.TextField(blank=True, default="")

    # Denormalized booleans for efficient filtering
    is_translated = models.BooleanField(default=False)
    is_fuzzy = models.BooleanField(default=False)
    obsolete = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        unique_together = [("language", "hash")]
        indexes = [
            models.Index(fields=["language", "order"]),
            models.Index(fields=["language", "is_translated", "is_fuzzy"]),
        ]

    def __str__(self) -> str:
        return self.msgid[:80]

    def save(self, *args, **kwargs) -> None:
        if not self.hash:
            self.hash = self.compute_hash(self.msgctxt, self.msgid)
        self._update_denormalized_fields()
        super().save(*args, **kwargs)

    @staticmethod
    def compute_hash(msgctxt: str, msgid: str) -> str:
        key = f"{msgctxt or ''}\x00{msgid}"
        return sha256(key.encode()).hexdigest()

    def get_absolute_url(self) -> str:
        return reverse(
            "jawcracker-translation-detail",
            kwargs={
                "language_id": self.language.language_name,
                "translation_id": self.hash,
            },
        )

    def _update_denormalized_fields(self) -> None:
        self.is_fuzzy = "fuzzy" in self.flags
        if self.msgid_plural:
            self.is_translated = bool(
                any(v.strip() for v in self.msgstr_plural.values())
            )
        else:
            self.is_translated = bool(self.msgstr.strip())
