from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings

import services.self_hosted as self_hosted
from codecov.commands.base import BaseInteractor
from services.decorators import torngit_safe
from services.repo_providers import get_generic_adapter_params, get_provider


@torngit_safe
@sync_to_async
def _is_admin_on_provider(owner, current_user):
    torngit_provider_adapter = get_provider(
        owner.service,
        {
            **get_generic_adapter_params(current_user, owner.service),
            **{
                "owner": {
                    "username": owner.username,
                    "service_id": owner.service_id,
                }
            },
        },
    )

    return async_to_sync(torngit_provider_adapter.get_is_admin)(
        user={
            "username": current_user.username,
            "service_id": current_user.service_id,
        }
    )


class GetIsCurrentUserAnAdminInteractor(BaseInteractor):
    @sync_to_async
    def execute(self, owner, current_owner):
        if settings.IS_ENTERPRISE:
            return self_hosted.is_admin_owner(current_owner)
        if not current_owner:
            return False
        if not hasattr(current_owner, "ownerid"):
            return False
        if owner.ownerid == current_owner.ownerid:
            return True
        admins = owner.admins
        try:
            isAdmin = async_to_sync(_is_admin_on_provider)(owner, current_owner)
            if isAdmin:
                # save admin provider in admins list
                owner.admins.append(current_owner.ownerid)
                owner.save()
            return isAdmin or (current_owner.ownerid in admins)
        except Exception as error:
            print(f"Error Calling Admin Provider {repr(error)}")
            return False
