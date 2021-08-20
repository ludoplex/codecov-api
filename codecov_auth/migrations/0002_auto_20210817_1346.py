# Generated by Django 3.1.6 on 2021-08-17 13:46

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_pull_user_provided_base_sha"),
        ("codecov_auth", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="owner",
            name="plan_provider",
            field=models.TextField(choices=[("github", "Github")], null=True),
        ),
        migrations.CreateModel(
            name="RepositoryToken",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("external_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token_type", models.CharField(max_length=50)),
                ("valid_until", models.DateTimeField(null=True)),
                ("key", models.CharField(max_length=40, unique=True)),
                (
                    "repository",
                    models.ForeignKey(
                        db_column="repoid",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tokens",
                        to="core.repository",
                    ),
                ),
            ],
            options={"abstract": False,},
        ),
    ]
