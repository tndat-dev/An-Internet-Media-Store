import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('product_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('product_type', models.CharField(choices=[('BOOK', 'Book'), ('CD', 'CD'), ('DVD', 'DVD'), ('NEWSPAPER', 'Newspaper')], max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('category', models.CharField(max_length=100)),
                ('general_description', models.TextField(blank=True)),
                ('height', models.DecimalField(decimal_places=2, max_digits=8)),
                ('width', models.DecimalField(decimal_places=2, max_digits=8)),
                ('length', models.DecimalField(decimal_places=2, max_digits=8)),
                ('weight', models.DecimalField(decimal_places=2, max_digits=8)),
                ('barcode', models.CharField(max_length=64, unique=True)),
                ('image_url', models.URLField(blank=True, max_length=500)),
                ('original_value', models.DecimalField(decimal_places=2, max_digits=12)),
                ('current_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('stock_quantity', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('DEACTIVATED', 'Deactivated'), ('DELETED', 'Deleted')], default='ACTIVE', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['title'],
            },
        ),
        migrations.CreateModel(
            name='Newspaper',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('publisher', models.CharField(blank=True, max_length=255)),
                ('publication_date', models.DateField(blank=True, null=True)),
                ('issue_number', models.CharField(blank=True, max_length=80)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='newspaper_details', to='products.product')),
            ],
        ),
        migrations.CreateModel(
            name='DVD',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('disc_type', models.CharField(blank=True, max_length=80)),
                ('director', models.CharField(blank=True, max_length=255)),
                ('runtime_minutes', models.PositiveIntegerField(blank=True, null=True)),
                ('studio', models.CharField(blank=True, max_length=255)),
                ('language', models.CharField(blank=True, max_length=80)),
                ('subtitles', models.CharField(blank=True, max_length=255)),
                ('release_date', models.DateField(blank=True, null=True)),
                ('genre', models.CharField(blank=True, max_length=100)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dvd_details', to='products.product')),
            ],
        ),
        migrations.CreateModel(
            name='CD',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('artists', models.CharField(max_length=255)),
                ('record_label', models.CharField(blank=True, max_length=255)),
                ('tracklist', models.TextField(blank=True)),
                ('genre', models.CharField(blank=True, max_length=100)),
                ('release_date', models.DateField(blank=True, null=True)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='cd_details', to='products.product')),
            ],
        ),
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('authors', models.CharField(max_length=255)),
                ('cover_type', models.CharField(blank=True, max_length=100)),
                ('publisher', models.CharField(blank=True, max_length=255)),
                ('publication_date', models.DateField(blank=True, null=True)),
                ('pages', models.PositiveIntegerField(blank=True, null=True)),
                ('language', models.CharField(blank=True, max_length=80)),
                ('genre', models.CharField(blank=True, max_length=100)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='book_details', to='products.product')),
            ],
        ),
        migrations.CreateModel(
            name='ProductHistory',
            fields=[
                ('history_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action_type', models.CharField(choices=[('CREATE', 'Create'), ('UPDATE', 'Update'), ('DELETE', 'Delete'), ('DEACTIVATE', 'Deactivate'), ('STOCK_ADJUST', 'Stock adjust')], max_length=20)),
                ('performed_by', models.CharField(default='manager', max_length=100)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='histories', to='products.product')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
