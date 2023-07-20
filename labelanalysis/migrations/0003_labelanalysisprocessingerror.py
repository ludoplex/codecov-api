# Generated by Django 4.2.2 on 2023-07-18 09:57

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labelanalysis", "0002_auto_20230208_1712"),
    ]

    # BEGIN;
    # --
    # -- Create model LabelAnalysisProcessingError
    # --
    # CREATE TABLE "labelanalysis_labelanalysisprocessingerror" ("id" bigint NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY, "external_id" uuid NOT NULL, "created_at" timestamp with time zone NOT NULL, "updated_at" timestamp with time zone NOT NULL, "error_code" varchar(100) NOT NULL, "error_params" jsonb NOT NULL, "label_analysis_request_id" bigint NOT NULL);
    # ALTER TABLE "labelanalysis_labelanalysisprocessingerror" ADD CONSTRAINT "labelanalysis_labela_label_analysis_reque_894742e5_fk_labelanal" FOREIGN KEY ("label_analysis_request_id") REFERENCES "labelanalysis_labelanalysisrequest" ("id") DEFERRABLE INITIALLY DEFERRED;
    # CREATE INDEX "labelanalysis_labelanalysi_label_analysis_request_id_894742e5" ON "labelanalysis_labelanalysisprocessingerror" ("label_analysis_request_id");
    # COMMIT;

    operations = [
        migrations.CreateModel(
            name="LabelAnalysisProcessingError",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("external_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("error_code", models.CharField(max_length=100)),
                ("error_params", models.JSONField(default=dict)),
                (
                    "label_analysis_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="errors",
                        to="labelanalysis.labelanalysisrequest",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]