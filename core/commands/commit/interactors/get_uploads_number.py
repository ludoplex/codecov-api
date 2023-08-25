from codecov.commands.base import BaseInteractor
from codecov.db import sync_to_async


class GetUploadsNumberInteractor(BaseInteractor):
    @sync_to_async
    def execute(self, commit):
        return len(commit.commitreport.sessions.all()) if commit.commitreport else 0
