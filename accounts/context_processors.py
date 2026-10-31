from django.conf import settings


def akun(request):
    return {"google_siap": bool(settings.GOOGLE_CLIENT_ID)}
