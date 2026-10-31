from django import template

register = template.Library()


@register.filter
def ambil(kamus, kunci):
    """{{ kamus|ambil:kunci }} — ambil nilai dict dengan kunci variabel."""
    try:
        return kamus.get(kunci)
    except AttributeError:
        return None
