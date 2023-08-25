from dataclasses import astuple, is_dataclass

from django.core.serializers.json import DjangoJSONEncoder


class ReportJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        return astuple(obj) if is_dataclass(obj) else super().default(self, obj)
