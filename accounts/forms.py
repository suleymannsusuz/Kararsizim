import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")

RESERVED_USERNAMES = {
    "admin", "kararsizim", "destek", "yonetim", "giris",
    "kayit", "cikis", "anket", "api", "static",
}


class RegisterForm(forms.Form):
    email = forms.EmailField(label="E-posta", max_length=254)
    username = forms.CharField(
        label="Kullanıcı adı",
        max_length=20,
        help_text="3–20 karakter; yalnızca harf (a-z), rakam, _ ve .",
    )
    password1 = forms.CharField(label="Parola", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Parola (tekrar)", strip=False, widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Bu e-posta adresi zaten kayıtlı.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if not USERNAME_RE.fullmatch(username):
            raise ValidationError(
                "Kullanıcı adı 3–20 karakter olmalı ve yalnızca a-z, 0-9, _ ve . içermelidir."
            )
        if username in RESERVED_USERNAMES:
            raise ValidationError("Bu kullanıcı adı kullanılamaz.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Bu kullanıcı adı zaten alınmış.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Parolalar eşleşmiyor.")
        elif password1:
            candidate = User(email=cleaned.get("email", ""), username=cleaned.get("username", ""))
            try:
                validate_password(password1, candidate)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
        )


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="E-posta",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Parola",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    error_messages = {
        "invalid_login": "E-posta veya parola hatalı.",
        "inactive": "Bu hesap devre dışı.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
