from django.db import models
from django.contrib.postgres.fields import ArrayField
from internal_api.repo.models import Repository
# from codecov_auth.models import Owner


class Branch(models.Model):
    name = models.TextField(primary_key=True, db_column='branch')
    repository = models.ForeignKey(Repository, db_column='repoid', on_delete=models.CASCADE, related_name='branches')
    # author = models.ForeignKey(Owner, db_column='authors', on_delete=models.CASCADE,)
    authors = ArrayField(models.IntegerField(null=True, blank=True), null=True, blank=True)
    head = models.CharField(max_length=256)
    updatestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'branches'
    pass