# Generated by Django 3.2.12 on 2022-09-07 17:38

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("codecov_auth", "0017_alter_organizationleveltoken_token_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserToken",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("external_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("token", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                (
                    "token_type",
                    models.CharField(
                        choices=[("api", "Api")], default="api", max_length=50
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        db_column="ownerid",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]