from codecov.commands.base import BaseInteractor
from codecov.db import sync_to_async
from codecov_auth.models import OrganizationLevelToken


class GetOrgUploadToken(BaseInteractor):
    @sync_to_async
    def execute(self, owner):
        if org_token := OrganizationLevelToken.objects.filter(owner=owner).first():
            return org_token.token
