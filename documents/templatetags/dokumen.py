from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def css_teks(nilai):
    """Aman dipakai di dalam string CSS: content: "{{ nilai|css_teks }}"."""
    teks = str(nilai or "")
    for asli, ganti in (("\\", "\\\\"), ('"', '\\"'), ("<", "\\3c "), ("\n", " "), ("\r", "")):
        teks = teks.replace(asli, ganti)
    return mark_safe(teks)
