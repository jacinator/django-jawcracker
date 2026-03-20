from __future__ import annotations

import json
from enum import IntFlag, auto
from typing import TYPE_CHECKING, Any, ClassVar

from django.db.models import Q
from django.http import Http404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views import generic

from .conf import settings
from .forms import TranslationForm
from .models import Language, Translation

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse

    from .conf import Settings


class LanguageListView(generic.TemplateView):
    extra_context: ClassVar[dict[str, Settings]] = {"jawcracker": settings}
    template_name: ClassVar[str] = "language_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("languages", self.get_languages())
        kwargs.setdefault("q", self.query)
        return super().get_context_data(**kwargs)

    def get_languages(self) -> QuerySet[Language]:
        qs: QuerySet[Language] = Language.objects.all()

        if query := self.query:
            qs = qs.filter(
                Q(language_name__icontains=query) | Q(locale_name__icontains=query)
            )

        return qs

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


class LanguageDetailView(LanguageListView):
    template_name: ClassVar[str] = "language_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("language", self.language)
        return super().get_context_data(**kwargs)

    @cached_property
    def language(self) -> Language:
        try:
            return Language.objects.get(
                language_name=self.kwargs["language_id"],
            )
        except Language.DoesNotExist as e:
            raise Http404(_("No language found")) from e


class Category(IntFlag):
    ALL = auto()
    FUZZY = auto()
    TRANSLATED = auto()
    UNTRANSLATED = auto()


class TranslationListView(LanguageDetailView):
    template_name: ClassVar[str] = "translation_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("translations", self.get_translations())
        return super().get_context_data(**kwargs)

    def get_translations(self) -> QuerySet[Translation]:
        qs: QuerySet[Translation] = Translation.objects.filter(
            language=self.language
        ).order_by("order")

        cat = self.category
        if cat is Category.FUZZY:
            qs = qs.filter(is_fuzzy=True)
        elif cat is Category.TRANSLATED:
            qs = qs.filter(is_translated=True, is_fuzzy=False)
        elif cat is Category.UNTRANSLATED:
            qs = qs.filter(is_translated=False)

        if query := self.query:
            qs = qs.filter(
                Q(msgid__icontains=query)
                | Q(msgid_plural__icontains=query)
                | Q(msgstr__icontains=query)
            )

        return qs

    @property
    def category(self) -> Category:
        try:
            return Category[self.request.GET["filter"].upper()]
        except KeyError:
            return Category.ALL


class TranslationDetailView(TranslationListView, generic.UpdateView):
    template_name: ClassVar[str] = "translation_detail.html"
    form_class: ClassVar[type] = TranslationForm

    def get_object(self, queryset=None) -> Translation:
        return self.translation

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(**kwargs))

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form: TranslationForm) -> HttpResponse:
        self.object = form.save()
        translation = Translation.objects.select_related("language").get(
            pk=self.object.pk,
        )
        return self.render_to_response(
            self.get_context_data(
                translation=translation,
                form=TranslationForm(instance=translation),
            )
        )

    def form_invalid(self, form: TranslationForm) -> HttpResponse:
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("translation", self.translation)
        kwargs.setdefault("form", self.get_form())
        return super().get_context_data(**kwargs)

    def hx_trigger(self) -> dict[str, Any]:
        current_order = self.translation.order
        language = self.language

        next_hash = (
            Translation.objects.filter(language=language, order__gt=current_order)
            .order_by("order")
            .values_list("hash", flat=True)
            .first()
        )
        prev_hash = (
            Translation.objects.filter(language=language, order__lt=current_order)
            .order_by("-order")
            .values_list("hash", flat=True)
            .first()
        )

        # Circular wrap-around
        if next_hash is None:
            next_hash = (
                Translation.objects.filter(language=language)
                .order_by("order")
                .values_list("hash", flat=True)
                .first()
            )
        if prev_hash is None:
            prev_hash = (
                Translation.objects.filter(language=language)
                .order_by("-order")
                .values_list("hash", flat=True)
                .first()
            )

        next_url = self._get_url(next_hash) if next_hash else None
        prev_url = self._get_url(prev_hash) if prev_hash else None

        event: dict[str, Any] = {
            "jawcracker:detail": {"nextUrl": next_url, "prevUrl": prev_url}
        }

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
        try:
            return Translation.objects.select_related("language").get(
                language=self.language,
                hash=self.kwargs["translation_id"],
            )
        except Translation.DoesNotExist as e:
            raise Http404(_("No translation found")) from e
