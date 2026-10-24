import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """Statik dosya adresine değişim zamanını ekler; dosya güncellenince tarayıcı eskisini kullanmaz."""
    url = static(path)
    found = finders.find(path)
    if isinstance(found, str):
        try:
            url += f"?v={int(os.path.getmtime(found))}"
        except OSError:
            pass
    return url


@register.filter
def avatar_color(username):
    """Kullanıcı adından deterministik, beyaz harfle yeterli kontrastlı bir renk üretir."""
    hue = sum(ord(char) * (index + 1) for index, char in enumerate(username)) % 360
    return f"hsl({hue} 65% 38%)"
