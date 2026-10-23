from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import MAX_OPTIONS, MIN_OPTIONS, Option, Poll

OPTION_TEXT_MAX = 60
VISIBLE_OPTION_ROWS = MAX_OPTIONS  # JS kapalıyken gösterilen alan sayısı


def _clean_text(value):
    return " ".join((value or "").split())


class PollForm(forms.Form):
    """Soru ve `options` adıyla tekrarlanan seçenek alanları.

    Seçenekler getlist ile okunur, böylece fazla alan gönderilirse sessizce
    kırpılmaz, reddedilir.
    """

    question = forms.CharField(
        label="Soru",
        min_length=5,
        max_length=140,
        widget=forms.TextInput(attrs={"data-counter": "140"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        submitted = self.data.getlist("options") if self.is_bound else []
        self.option_rows = submitted + [""] * (VISIBLE_OPTION_ROWS - len(submitted))

    def clean_question(self):
        question = _clean_text(self.cleaned_data["question"])
        if len(question) < 5:
            raise ValidationError("Soru en az 5 karakter olmalı.")
        return question

    def clean(self):
        cleaned = super().clean()
        options = [_clean_text(raw) for raw in self.option_rows]
        options = [text for text in options if text]

        if any(len(text) > OPTION_TEXT_MAX for text in options):
            raise ValidationError(f"Her seçenek en fazla {OPTION_TEXT_MAX} karakter olabilir.")
        if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise ValidationError(f"Anket {MIN_OPTIONS} ile {MAX_OPTIONS} arasında seçenek içermeli.")
        if len({text.casefold() for text in options}) != len(options):
            raise ValidationError("Aynı seçenek birden fazla kez girilemez.")

        cleaned["options"] = options
        return cleaned

    @transaction.atomic
    def save(self, author):
        poll = Poll.objects.create(author=author, question=self.cleaned_data["question"])
        Option.objects.bulk_create(
            Option(poll=poll, text=text, position=position)
            for position, text in enumerate(self.cleaned_data["options"])
        )
        return poll
