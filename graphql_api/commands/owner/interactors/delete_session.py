from asgiref.sync import sync_to_async

from codecov_auth.models import Session
from codecov.commands.base import BaseInteractor
from codecov.commands.exceptions import Unauthenticated


class DeleteSessionInteractor(BaseInteractor):
    def validate(self):
        if not self.current_user.is_authenticated:
            raise Unauthenticated()

    @sync_to_async
    def execute(self, sessionid):
        self.validate()
        Session.objects.filter(sessionid=sessionid, owner=self.current_user).delete()
