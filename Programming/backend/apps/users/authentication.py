"""Custom token authentication for internal users (apps.users.User).

DRF's built-in TokenAuthentication is bound to AUTH_USER_MODEL (django.contrib
.auth.User). AIMS keeps a separate application identity model, so this class
resolves an opaque "Authorization: Token <key>" header to an apps.users.User.

It only authenticates when a token is present; absent/invalid tokens leave the
request anonymous rather than rejecting it, so AllowAny endpoints keep working.
"""

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from apps.users.models import AuthToken, UserStatusChoice


class UsersTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None  # no token -> stay anonymous (AllowAny endpoints still work)
        if len(auth) == 1:
            raise exceptions.AuthenticationFailed("Invalid token header. No credentials provided.")
        if len(auth) > 2:
            raise exceptions.AuthenticationFailed("Invalid token header. Token string should not contain spaces.")

        try:
            key = auth[1].decode()
        except UnicodeError as exc:
            raise exceptions.AuthenticationFailed("Invalid token header. Token contains invalid characters.") from exc

        try:
            token = AuthToken.objects.select_related("user").get(key=key)
        except AuthToken.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc

        if token.user.status != UserStatusChoice.ACTIVE:
            raise exceptions.AuthenticationFailed("User account is not active.")

        return (token.user, token)

    def authenticate_header(self, request):
        return self.keyword
