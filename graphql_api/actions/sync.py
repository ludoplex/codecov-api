from asgiref.sync import sync_to_async

from services.refresh import RefreshService
from codecov.commands.exceptions import Unauthenticated


@sync_to_async
def is_syncing(current_user):
    return RefreshService().is_refreshing(current_user.ownerid)


@sync_to_async
def trigger_sync(current_user):
    if not current_user.is_authenticated:
        raise Unauthenticated()
    RefreshService().trigger_refresh(
        current_user.ownerid,
        current_user.username,
        using_integration=bool(current_user.integration_id),
    )
    return {}
