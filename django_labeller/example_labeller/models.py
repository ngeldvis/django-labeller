from django.db import models

from image_labelling_tool import models as lt_models
import django.utils.timezone

# Create your models here.

class ImageWithLabels (models.Model):
    url = models.CharField(max_length=150)
    width = models.IntegerField()
    height = models.IntegerField()
    labels = models.ForeignKey(lt_models.Labels, models.CASCADE, related_name='image')

    def get_name(self):
        return self.url.split('/')[-1]


class DextrTask (models.Model):
    image = models.ForeignKey(ImageWithLabels, models.CASCADE)
    dextr_id = models.IntegerField()
    image_id_str = models.CharField(max_length=128)
    celery_task_id = models.CharField(max_length=128)
    creation_timestamp = models.DateTimeField(default=django.utils.timezone.now)

