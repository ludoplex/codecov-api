from codecov.commands.base import BaseInteractor
from codecov.db import sync_to_async
from graphql_api.types.enums import UploadState
from reports.models import UploadError


class GetUploadErrorInteractor(BaseInteractor):
    @sync_to_async
    def execute(self, report_session):
        if report_session.state != UploadState.ERROR.value:
            return UploadError.objects.none()

        return UploadError.objects.filter(report_session=report_session.id)
