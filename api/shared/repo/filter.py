from django_filters import BooleanFilter
from django_filters import rest_framework as django_filters

from core.models import Repository


class StringListFilter(django_filters.Filter):
    def __init__(self, query_param, *args, **kwargs):
        super(StringListFilter, self).__init__(*args, **kwargs)
        self.query_param = query_param

    def filter(self, qs, value):
        try:
            request = self.parent.request
        except AttributeError:
            return None

        values = request.GET.getlist(self.query_param)
        if len(values) > 0:
            return qs.filter(**{f"{self.field_name}__{self.lookup_expr}": values})

        return qs


class RepositoryFilters(django_filters.FilterSet):
    """Filter for active repositories"""

    active = BooleanFilter(
        field_name="active",
        method="filter_active",
        label="whether the repository has received an upload",
    )

    """Filter for getting multiple repositories by name"""
    names = StringListFilter(
        query_param="names",
        field_name="name",
        lookup_expr="in",
        label="list of repository names",
    )

    def filter_active(self, queryset, name, value):
        # The database currently stores 't' instead of 'true' for active repos, and nothing for inactive
        # so if the query param active is set, we return repos with non-null value in active column
        return queryset.filter(active=value)

    class Meta:
        model = Repository
        fields = ["active", "names"]
