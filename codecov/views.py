from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect

from core.models import Constants


def health(request):
    version = Constants.objects.get(key="version")
    return HttpResponse(f"{version.value} is live!")


def redirect_app(request):
    """
    This view is intended to be used as part of the frontend migration to redirect traffic from legacy urls to urls
    """
    app_domain = settings.CODECOV_DASHBOARD_URL
    return HttpResponseRedirect(app_domain + request.path.replace("/redirect_app", ""))
