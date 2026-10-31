from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def menunggu(request):
    if not request.user.menunggu_peran:
        return redirect("beranda")
    return render(request, "accounts/menunggu.html")
