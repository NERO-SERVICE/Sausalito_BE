from __future__ import annotations

from django.db import migrations


def seed_bank_transfer_account_config(apps, schema_editor):
    del schema_editor
    BankTransferAccountConfig = apps.get_model("payments", "BankTransferAccountConfig")
    BankTransferAccountConfig.objects.get_or_create(singleton_key=1)


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_banktransferaccountconfig"),
    ]

    operations = [
        migrations.RunPython(seed_bank_transfer_account_config, migrations.RunPython.noop),
    ]
