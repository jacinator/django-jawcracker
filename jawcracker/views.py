from __future__ import annotations

import json
from enum import IntFlag, auto
from typing import TYPE_CHECKING, Any, ClassVar

from django.http import Http404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views import generic

from .conf import settings
from .objects import LanguageManager, TranslationManager

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.http import HttpRequest, HttpResponse
    from polib import POEntry

    from .conf import Settings
    from .objects import Language, Translation


class LanguageListView(generic.TemplateView):
    extra_context: ClassVar[dict[str, Settings]] = {"jawcracker": settings}
    template_name: ClassVar[str] = "language_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("languages", self.get_languages())
        kwargs.setdefault("q", self.query)
        return super().get_context_data(**kwargs)

    def get_languages(self) -> Iterable[Language]:
        items: Iterable[Language] = self.languages.values()

        if query := self.query:
            items = (x for x in items if query in x)

        return items

    def get_template_names(self) -> list[str]:
        if self.htmx:
            return [f"jawcracker/fragments/{self.template_name}"]
        return [f"jawcracker/{self.template_name}"]

    @property
    def htmx(self) -> bool:
        return self.request.headers.get("HX-Request", "false") == "true"

    @property
    def query(self) -> str:
        return self.request.GET.get("q", "").strip()

    @cached_property
    def languages(self) -> LanguageManager:
        return LanguageManager()


class LanguageDetailView(LanguageListView):
    template_name: ClassVar[str] = "language_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("language", self.language)
        return super().get_context_data(**kwargs)

    @cached_property
    def language(self) -> Language:
        try:
            return self.languages[self.kwargs["language_id"]]
        except KeyError as e:
            raise Http404(_("No language found")) from e


class Category(IntFlag):
    ALL = auto()
    FUZZY = auto()
    TRANSLATED = auto()
    UNTRANSLATED = auto()

    def filter(self, entry: POEntry) -> bool:
        return (
            (self is Category.ALL)
            or (self is Category.FUZZY and entry.fuzzy)
            or (self is Category.TRANSLATED and entry.translated and not entry.fuzzy)
            or (self is Category.UNTRANSLATED and not entry.translated)
        )


class TranslationListView(LanguageDetailView):
    template_name: ClassVar[str] = "translation_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("translations", self.get_translations())
        return super().get_context_data(**kwargs)

    def get_translations(self) -> Iterable[Translation]:
        items: Iterable[Translation] = self.translations.values()

        if query := self.query:
            items = (x for x in items if query in x)

        return (x for x in items if self.category.filter(x.entry))

    @property
    def category(self) -> Category:
        try:
            return Category[self.request.GET["filter"].upper()]
        except KeyError:
            return Category.ALL

    @cached_property
    def translations(self) -> TranslationManager:
        return TranslationManager(self.language)


class TranslationDetailView(TranslationListView):
    template_name: ClassVar[str] = "translation_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("translation", self.translation)
        return super().get_context_data(**kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if self.translation.entry.msgid_plural:
            self.translation.entry.msgstr_plural |= {
                int(x.removeprefix("msgstr_")): y
                for x, y in request.POST.items()
                if x.startswith("msgstr_")
            }
        else:
            self.translation.entry.msgstr = request.POST.get("msgstr", "")

        if "fuzzy" in self.translation.entry.flags:
            self.translation.entry.flags.remove("fuzzy")

        self.translations.pofile.save()
        translation: Translation = self.translations[kwargs["translation_id"]]

        return super().get(request, *args, translation=translation, **kwargs)

    def hx_trigger(self) -> dict[str, dict[str, str]]:
        next_url: str | None = None
        if next_id := self.translations.get_next(self.kwargs["translation_id"]):
            next_url = self._get_url(next_id)

        prev_url: str | None = None
        if prev_id := self.translations.get_previous(self.kwargs["translation_id"]):
            prev_url = self._get_url(prev_id)

        event = {"jawcracker:detail": {"nextUrl": next_url, "prevUrl": prev_url}}

        if self.request.method == "POST":
            event["jawcracker:saved"] = True

        return event

    def render_to_response(
        self, context: dict[str, Any], **response_kwargs: Any
    ) -> HttpResponse:
        if self.htmx:
            headers: dict[str, str] = response_kwargs.get("headers", {})

            headers.setdefault("HX-Trigger-After-Swap", json.dumps(self.hx_trigger()))

            response_kwargs["headers"] = headers
        return super().render_to_response(context, **response_kwargs)

    def _get_url(self, translation_id: str) -> str:
        return reverse(
            "jawcracker-translation-detail",
            kwargs={
                "language_id": self.kwargs["language_id"],
                "translation_id": translation_id,
            },
        )

    @cached_property
    def translation(self) -> Translation:
        return self.translations[self.kwargs["translation_id"]]
