import logging

from asgiref.sync import async_to_sync
from django.http import Http404
from rest_framework.permissions import SAFE_METHODS  # ['GET', 'HEAD', 'OPTIONS']
from rest_framework.permissions import BasePermission

from api.shared.mixins import InternalPermissionsMixin, SuperPermissionsMixin
from api.shared.repo.repository_accessors import RepoAccessors
from services.activation import try_auto_activate
from services.decorators import torngit_safe
from services.repo_providers import get_generic_adapter_params, get_provider

log = logging.getLogger(__name__)


class RepositoryPermissionsService:
    @torngit_safe
    def _fetch_provider_permissions(self, owner, repo):
        can_view, can_edit = RepoAccessors().get_repo_permissions(owner, repo)

        if can_view:
            owner.permission = owner.permission or []
            owner.permission.append(repo.repoid)
            owner.save(update_fields=["permission"])

        return can_view, can_edit

    def has_read_permissions(self, owner, repo):
        return not repo.private or (
            owner is not None
            and (
                repo.author.ownerid == owner.ownerid
                or owner.permission
                and repo.repoid in owner.permission
                or self._fetch_provider_permissions(owner, repo)[0]
            )
        )

    def has_write_permissions(self, user, repo):
        return user.is_authenticated and (
            repo.author.ownerid == user.ownerid
            or self._fetch_provider_permissions(user, repo)[1]
        )

    def user_is_activated(self, current_owner, owner):
        if current_owner.ownerid == owner.ownerid:
            return True
        if owner.has_legacy_plan:
            return True
        if (
            current_owner.organizations is None
            or owner.ownerid not in current_owner.organizations
        ):
            return False
        if (
            owner.plan_activated_users
            and current_owner.ownerid in owner.plan_activated_users
        ):
            return True
        return try_auto_activate(owner, current_owner)


class RepositoryArtifactPermissions(BasePermission):
    """
    Permissions class for artifacts of a repository, eg commits, branches,
    pulls, comparisons, etc. Requires that the view has a '.repo'
    property that returns the repo being worked on.
    """

    permissions_service = RepositoryPermissionsService()
    message = (
        f"Permission denied: some possible reasons for this are (1) the "
        f"user doesn't have permission to view the specific resource, "
        f"(2) the organization has a per-user plan or (3) the user is "
        f"trying to view a private repo but is not activated."
    )

    def has_permission(self, request, view):
        if view.repo.private:
            user_activated_permissions = (
                request.user.is_authenticated
                and self.permissions_service.user_is_activated(
                    request.current_owner, view.owner
                )
            )
        else:
            user_activated_permissions = True
        if has_read_permissions := (
            request.method in SAFE_METHODS
            and self.permissions_service.has_read_permissions(
                request.current_owner, view.repo
            )
        ):
            return bool(user_activated_permissions)
        raise Http404()


class SuperTokenPermissions(BasePermission, SuperPermissionsMixin):
    def has_permission(self, request, view):
        return self.has_super_token_permissions(request)


class InternalTokenPermissions(BasePermission, InternalPermissionsMixin):
    def has_permission(self, request, view):
        return self.has_internal_token_permissions(request)


class ChartPermissions(BasePermission):
    permissions_service = RepositoryPermissionsService()

    def has_permission(self, request, view):
        log.info(
            f"Coverage chart has repositories {view.repositories}",
            extra=dict(user=request.current_owner),
        )
        for repo in view.repositories:
            # TODO: this can cause a provider-api request for every repo in the list,
            # can we just rely on our stored read permissions? In fact, it seems like
            # permissioning is built into api.internal.charts.filter.add_simple_filters
            if not self.permissions_service.has_read_permissions(
                request.current_owner, repo
            ):
                raise Http404
        return True


class UserIsAdminPermissions(BasePermission):
    """
    Permissions class for asserting the user is an admin of the 'owner'
    being queried. Requires that the view has a '.owner' property that
    returns this owner.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.current_owner
            and (
                view.owner.is_admin(request.current_owner)
                or self._is_admin_on_provider(request.current_owner, view.owner)
            )
        )

    @torngit_safe
    def _is_admin_on_provider(self, user, owner):
        torngit_provider_adapter = get_provider(
            owner.service,
            {
                **get_generic_adapter_params(user, owner.service),
                **{
                    "owner": {
                        "username": owner.username,
                        "service_id": owner.service_id,
                    }
                },
            },
        )

        return async_to_sync(torngit_provider_adapter.get_is_admin)(
            user={"username": user.username, "service_id": user.service_id}
        )


class MemberOfOrgPermissions(BasePermission):
    """
    Permissions class for asserting the user is member of the owner.
    Requires that the view has a '.owner' property that returns this owner.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        current_owner = request.current_owner
        if not current_owner:
            return False

        owner = view.owner
        if current_owner == owner:
            return True
        if owner.ownerid in (current_owner.organizations or []):
            return True
        else:
            raise Http404("No Owner matches the given query.")
