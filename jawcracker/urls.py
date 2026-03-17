from django.urls import path

from .views import (
    LanguageDetailView,
    LanguageListView,
    TranslationDetailView,
    TranslationListView,
)

urlpatterns = [
    path(
        "",
        LanguageListView.as_view(),
        name="jawcracker-language-list",
    ),
    path(
        "<slug:language_id>/fragment/",
        LanguageDetailView.as_view(),
        name="jawcracker-language-detail",
    ),
    path(
        "<slug:language_id>/",
        TranslationListView.as_view(),
        name="jawcracker-translation-list",
    ),
    path(
        "<slug:language_id>/<str:translation_id>/fragment/",
        TranslationDetailView.as_view(),
        name="jawcracker-translation-detail",
    ),
]
