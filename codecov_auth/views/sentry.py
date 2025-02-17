import logging
from typing import Dict, Optional
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views import View

from codecov_auth.models import SentryUser, User
from codecov_auth.views.base import LoginMixin
from utils.services import get_short_service_name

log = logging.getLogger(__name__)


OAUTH_AUTHORIZE_URL = "https://sentry.io/oauth/authorize"
OAUTH_TOKEN_URL = (
    "https://sentry.io/oauth/token/"  # seems to require the trailing slash
)


class SentryLoginView(LoginMixin, View):
    def _fetch_user_data(self, code: str) -> Optional[Dict]:
        res = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.SENTRY_OAUTH_CLIENT_ID,
                "client_secret": settings.SENTRY_OAUTH_CLIENT_SECRET,
                "code": code,
            },
        )

        return None if res.status_code >= 400 else res.json()

    def _redirect_to_consent(self) -> HttpResponse:
        qs = urlencode(
            dict(
                response_type="code",
                client_id=settings.SENTRY_OAUTH_CLIENT_ID,
                scope="openid email profile",
            )
        )
        redirect_url = f"{OAUTH_AUTHORIZE_URL}?{qs}"
        response = redirect(redirect_url)
        self.store_to_cookie_utm_tags(response)
        return response

    def _perform_login(self, request: HttpRequest) -> HttpResponse:
        code = request.GET.get("code")
        user_data = self._fetch_user_data(code)
        if user_data is None:
            log.warning("Unable to log in due to problem on Sentry", exc_info=True)
            return redirect(f"{settings.CODECOV_DASHBOARD_URL}/login")

        # TODO: verify `id_token` by decoding the JWT using our shared secret

        current_user = self._login_user(request, user_data)

        # TEMPORARY: we're assuming a single owner for the time being since there's
        # no supporting UI to select which owner you'd like to view
        owner = current_user.owners.first()
        if owner is None:
            # user has not connected any owners yet
            return redirect(f"{settings.CODECOV_DASHBOARD_URL}/sync")
        service = get_short_service_name(owner.service)
        return redirect(f"{settings.CODECOV_DASHBOARD_URL}/{service}")

    def _login_user(self, request: HttpRequest, user_data: dict):
        sentry_id = user_data["user"]["id"]
        user_name = user_data["user"].get("name")
        user_email = user_data["user"].get("email")

        sentry_user = SentryUser.objects.filter(sentry_id=sentry_id).first()

        current_user = None
        if request.user is not None and not request.user.is_anonymous:
            # we're already authenticated
            current_user = request.user

            if sentry_user and sentry_user.user != request.user:
                log.warning(
                    "Sentry account already linked to another user",
                    extra=dict(
                        current_user_id=request.user.pk, sentry_user_id=sentry_user.pk
                    ),
                )
                # Logout the current user and login the user who already
                # claimed this Sentry account (below)
                logout(request)
                current_user = sentry_user.user
        elif sentry_user:
            log.info(
                "Existing Sentry user logging in",
                extra=dict(sentry_user_id=sentry_user.pk),
            )
            current_user = sentry_user.user
        else:
            current_user = User.objects.create(
                name=user_name,
                email=user_email,
            )

        if sentry_user is None:
            sentry_user = SentryUser.objects.create(
                user=current_user,
                sentry_id=sentry_id,
                name=user_name,
                email=user_email,
                access_token=user_data["access_token"],
                refresh_token=user_data["refresh_token"],
            )
            log.info(
                "Created Sentry user",
                extra=dict(sentry_user_id=sentry_user.pk),
            )

        login(request, current_user)
        return current_user

    def get(self, request):
        if request.GET.get("code"):
            return self._perform_login(request)
        else:
            return self._redirect_to_consent()
