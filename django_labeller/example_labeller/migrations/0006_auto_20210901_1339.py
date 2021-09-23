# Generated by Django 3.2.6 on 2021-09-01 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('example_labeller', '0005_photo_photoannotation'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='photoannotation',
            name='photo_id',
        ),
        migrations.AddField(
            model_name='imagewithlabels',
            name='url',
            field=models.CharField(default='localhost', max_length=150),
            preserve_default=False,
        ),
        migrations.DeleteModel(
            name='Photo',
        ),
        migrations.DeleteModel(
            name='PhotoAnnotation',
        ),
    ]
