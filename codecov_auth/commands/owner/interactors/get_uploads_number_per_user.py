from datetime import timedelta

from django.utils import timezone

from codecov.commands.base import BaseInteractor
from codecov.db import sync_to_async
from codecov_auth.models import Owner
from plan.constants import USER_PLAN_REPRESENTATIONS
from plan.service import PlanService
from reports.models import ReportSession


class GetUploadsNumberPerUserInteractor(BaseInteractor):
    @sync_to_async
    def execute(self, owner: Owner):
        plan_service = PlanService(current_org=owner)
        monthly_limit = plan_service.monthly_uploads_limit
        if monthly_limit is not None:
            return ReportSession.objects.filter(
                report__commit__repository__author_id=owner.ownerid,
                report__commit__repository__private=True,
                created_at__gte=timezone.now() - timedelta(days=30),
                report__commit__timestamp__gte=timezone.now() - timedelta(days=60),
                upload_type="uploaded",
            )[:monthly_limit].count()
