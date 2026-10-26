import unicodedata

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import MAX_OPTIONS, MIN_OPTIONS, Option, Poll

OPTION_TEXT_MAX = 60
VISIBLE_OPTION_ROWS = MAX_OPTIONS  # JS kapalıyken gösterilen alan sayısı


INVALID_TEXT_MESSAGE = "Metinde görünmez ya da kontrol karakterleri olamaz."
ALLOWED_FORMAT_CHARS = {"‌", "‍"}  # emoji birleştiricisi (👨‍👩‍👧 gibi) için


def _clean_text(value):
    return " ".join((value or "").split())


def _has_invalid_chars(text):
    """NUL/kontrol karakterleri (Postgres NUL'u reddeder) ve görünmez biçim karakterleri (sıfır genişlikli boşluk, yön değiştirici)."""
    for char in text:
        category = unicodedata.category(char)
        if category == "Cc" or (category == "Cf" and char not in ALLOWED_FORMAT_CHARS):
            return True
    return False


def _is_visible(text):
    return any(char.isprintable() and not char.isspace() for char in text)


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
        self.submitted_options = self.data.getlist("options") if self.is_bound else []
        # Formda yalnızca ilk satırlar geri gösterilir; fazlası doğrulamada reddedilir, sayfaya yansıtılmaz.
        shown = self.submitted_options[:VISIBLE_OPTION_ROWS]
        self.option_rows = shown + [""] * (VISIBLE_OPTION_ROWS - len(shown))

    def clean_question(self):
        question = _clean_text(self.cleaned_data["question"])
        if len(question) < 5:
            raise ValidationError("Soru en az 5 karakter olmalı.")
        if _has_invalid_chars(question) or not _is_visible(question):
            raise ValidationError(INVALID_TEXT_MESSAGE)
        return question

    def clean(self):
        cleaned = super().clean()
        count_message = f"Anket {MIN_OPTIONS} ile {MAX_OPTIONS} arasında seçenek içermeli."
        if len(self.submitted_options) > MAX_OPTIONS:
            raise ValidationError(count_message)

        options = [_clean_text(raw) for raw in self.submitted_options]
        options = [text for text in options if text]

        if any(len(text) > OPTION_TEXT_MAX for text in options):
            raise ValidationError(f"Her seçenek en fazla {OPTION_TEXT_MAX} karakter olabilir.")
        if any(_has_invalid_chars(text) or not _is_visible(text) for text in options):
            raise ValidationError(INVALID_TEXT_MESSAGE)
        if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise ValidationError(count_message)
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
