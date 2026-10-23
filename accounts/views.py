from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db import IntegrityError
from django.shortcuts import redirect, render

from .forms import LoginForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            # Aynı anda gelen kayıtlarda form kontrolünü geçen ama DB'de çakışan durum.
            form.add_error(None, "Bu e-posta veya kullanıcı adı zaten kayıtlı.")
        else:
            login(request, user)
            messages.success(request, f"Hoş geldin, @{user.username}!")
            return redirect("home")
    return render(request, "accounts/register.html", {"form": form})


class SignInView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
