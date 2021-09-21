import numpy as np
import os
import urllib.request

from celery import shared_task
from image_labelling_tool import labelling_tool

from django.conf import settings


_dextr_model = None

def _apply_dextr(image_path, dextr_points_np):
    global _dextr_model
    if settings.LABELLING_TOOL_DEXTR_AVAILABLE or settings.LABELLING_TOOL_DEXTR_WEIGHTS_PATH is not None:
        if _dextr_model is None:
            from dextr.model import DextrModel
            import torch

            device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

            if settings.LABELLING_TOOL_DEXTR_WEIGHTS_PATH is not None:
                dextr_weights = os.path.expanduser(settings.LABELLING_TOOL_DEXTR_WEIGHTS_PATH)
                dextr_model = torch.load(dextr_weights, map_location=device)
            else:
                dextr_model = DextrModel.pascalvoc_resunet101().to(device)

            dextr_model.eval()

            _dextr_model = dextr_model

        from PIL import Image

        image_file_path, _ = urllib.request.urlretrieve(image_path)
        im = Image.open(image_file_path)

        mask = _dextr_model.predict([im], dextr_points_np[None, :, :])[0] >= 0.5
        regions = labelling_tool.PolygonLabel.mask_image_to_regions_cv(mask, sort_decreasing_area=True)
        regions_js = labelling_tool.PolygonLabel.regions_to_json(regions)

        os.remove(image_file_path)

        return regions_js
    else:
        return None


@shared_task
def test_task(a, b):
    return a + b

@shared_task
def dextr(image_path, dextr_points_js):
    dextr_points = np.array([[p['y'], p['x']] for p in dextr_points_js])
    regions_js = _apply_dextr(image_path, dextr_points)
    return regions_js
