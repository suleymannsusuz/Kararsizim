from django import template

register = template.Library()


@register.filter
def avatar_color(username):
    """Kullanıcı adından deterministik, beyaz harfle yeterli kontrastlı bir renk üretir."""
    hue = sum(ord(char) * (index + 1) for index, char in enumerate(username)) % 360
    return f"hsl({hue} 65% 38%)"
