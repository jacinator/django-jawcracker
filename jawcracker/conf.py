from dataclasses import dataclass, field
from typing import Final

from django.conf import settings as django_settings
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _


def _get_setting(name: str, default: str) -> str:
    if jawcracker := getattr(django_settings, "JAWCRACKER", None):
        return jawcracker.get(name, default)
    return default


@lazy
def _get_primary() -> str:
    return _get_setting("primary", "#4E41AE")


@lazy
def _get_title() -> str:
    return _get_setting("title", _("Jawcracker"))


@dataclass(frozen=True, slots=True)
class Settings:
    primary: str = field(default_factory=_get_primary, init=False)
    title: str = field(default_factory=_get_title, init=False)


settings: Final[Settings] = Settings()
