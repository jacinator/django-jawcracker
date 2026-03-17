# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-jawcracker is a reusable Django app for managing translation .po files via a web UI. It has **no database** — it reads and writes .po files directly from disk using the `polib` library. It discovers .po files via Django's `LOCALE_PATHS` setting.

## Development Setup

```bash
pip install -e ".[dev]"    # Install with dev dependencies (pytest, pytest-django)
```

## Architecture

This is a single Django app (`jawcracker/`) designed to be installed into a host Django project.

### Key modules

- **objects.py** — Domain models (no Django ORM). `Language` and `Translation` are the core entities, with `LanguageManager` and `TranslationManager` providing mapping/lookup interfaces over .po files. Translations are identified by SHA256 hash of `msgctxt+msgid`.
- **views.py** — Class-based views using `TemplateView`. All views detect HTMX requests (`HX-Request` header) and return fragment templates instead of full pages. `TranslationDetailView` handles POST to save translations back to .po files.
- **conf.py** — Lazy-loaded settings from `django.conf.settings.JAWCRACKER` dict. Configurable: `primary` (theme color), `title`.
- **urls.py** — Four URL patterns: language list, language detail (fragment), translation list, translation detail (fragment).

### Frontend

HTMX-driven UI with no full page reloads. Templates use a base/includes/fragments pattern:
- `templates/jawcracker/` — Full page templates
- `templates/jawcracker/includes/` — Reusable template partials
- `templates/jawcracker/fragments/` — HTMX response fragments with OOB swaps

Static JS (`jawcracker.js`) provides keyboard navigation (j/k), toast notifications, and scroll-to-active behavior. Uses `idiomorph` extension for HTMX DOM morphing.

### Integration

A host Django project includes this app by:
1. Adding `'jawcracker'` to `INSTALLED_APPS`
2. Setting `LOCALE_PATHS` in settings
3. Including `jawcracker.urls` in the URLconf
