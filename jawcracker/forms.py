from __future__ import annotations

from django import forms

from .models import Translation


class TranslationForm(forms.ModelForm):
    class Meta:
        model = Translation
        fields = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance.msgid_plural:
            for key in sorted(instance.msgstr_plural, key=int):
                field_name = f"msgstr_{key}"
                self.fields[field_name] = forms.CharField(
                    widget=forms.Textarea(attrs={"rows": 3, "id": f"msgstr_{key}"}),
                    required=False,
                    initial=instance.msgstr_plural.get(key, ""),
                )
        else:
            self.fields["msgstr"] = forms.CharField(
                widget=forms.Textarea(attrs={"rows": 3, "id": "msgstr"}),
                required=False,
                initial=instance.msgstr,
            )

    @property
    def plural_fields(self):
        """Return plural form fields in order, for template iteration."""
        return [
            self[f"msgstr_{key}"]
            for key in sorted(self.instance.msgstr_plural, key=int)
        ]

    def save(self, commit=True):
        instance = self.instance
        if instance.msgid_plural:
            instance.msgstr_plural = {
                key: self.cleaned_data.get(f"msgstr_{key}", "")
                for key in instance.msgstr_plural
            }
        else:
            instance.msgstr = self.cleaned_data.get("msgstr", "")

        if "fuzzy" in instance.flags:
            instance.flags = [f for f in instance.flags if f != "fuzzy"]

        if commit:
            instance.save()
        return instance
