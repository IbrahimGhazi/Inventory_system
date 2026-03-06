from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='PendingSync',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation', models.CharField(choices=[('upsert', 'Upsert'), ('delete', 'Delete')], max_length=10)),
                ('table_name', models.CharField(max_length=100)),
                ('record_id', models.CharField(max_length=200)),
                ('app_label', models.CharField(blank=True, max_length=100)),
                ('model_name', models.CharField(blank=True, max_length=100)),
                ('local_pk', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Pending Sync',
                'verbose_name_plural': 'Pending Syncs',
                'ordering': ['created_at'],
            },
        ),
    ]
