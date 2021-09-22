import json
import numpy as np
import uuid
import pathlib, math

from datetime import datetime
from pprint import pprint
from pycocotools import mask as masktool

from image_labelling_tool import labelled_image, labelling_tool

def set_to_range(bbox, w,h):
    s_x,s_y,b_w,b_h = bbox
    s_x = max(s_x,0)
    s_y = max(s_y,0)
    b_w = min(b_w+s_x,w)-s_x
    b_h = min(b_h+s_y,h)-s_y
    
    return [s_x,s_y,b_w,b_h]

def django2coco(labelled_images, class_labelling_scheme, ds_info, licenses=None):
    ann_id = 1
    current_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    images = []
    annotations = []
    categories = []
    if licenses is None:
        licenses = [{"url": "", "id": 1, "name": "Default License"}]

    for key, value in class_labelling_scheme.items():
        if key is not None and key != "null":
            categories.append({"id": value, "name": key, "supercategory": "gls"})

    for img_id, limg in enumerate(labelled_images):
        img_dict = {
            "license": 1,
            "file_name": limg.image_source.name,
            "coco_url": "",
            "flickr_url": "",
            "date_captured": current_datetime,
            "height": limg.image_source.size[0],
            "width": limg.image_source.size[1],
            "id": img_id,
        }
        images.append(img_dict)

        labels = []
        for label in limg.labels.labels:
            if isinstance(label, labelling_tool.BoxLabel):
                labels.append(label.to_polygon())
            elif isinstance(label, labelling_tool.OrientedEllipseLabel):
                labels.append(label.to_polygon())
            else:
                labels.append(label)

        for label in labels:
            if label.classification not in class_labelling_scheme.keys():
                continue
            if not hasattr(label, 'regions'):
                continue
            try:
                category_id =  0
                if (label.classification is not None) and label.classification != "null":
                    category_id = class_labelling_scheme[label.classification]

                # changes segmentation instance from numpy to list format
                segmentation = [list(np.hstack(i)) for i in label.regions]
                # convert from xyxy to xywh
                bbox = list(label.bounding_box()[0]) + list(label.bounding_box()[1] - label.bounding_box()[0])
                
                # use pycocotools to compute mask area
                mask_area = int(
                    np.sum(
                        masktool.area(
                            masktool.frPyObjects(
                                segmentation,
                                img_dict["height"],
                                img_dict["width"],
                            )
                        )
                    )
                )

                ann_dict = {
                    "segmentation": segmentation,
                    "id": ann_id,
                    "category_id": category_id,
                    "image_id": img_id,
                    "iscrowd": 0,
                    "bbox": bbox,
                    "area": mask_area,
                }

                ann_dict["bbox"] = set_to_range(ann_dict["bbox"], img_dict['height'], img_dict['width'])
                annotations.append(ann_dict)
                ann_id += 1
            except Exception as e:
                print(e)
                exit()

    coco = {
        "info": ds_info,
        "images": images,
        "licenses": licenses,
        "categories": categories,
        "annotations": annotations,
    }
    return json.dumps(coco, indent=4)

def coco2django(coco_json_str, class_labelling_scheme, source='coco') -> str:
    coco_json = json.loads(coco_json_str)

    categories = {cat['id']: cat['name'] for cat in coco_json['categories']}

    labels = []
    for annotation in coco_json['annotations']:
        cat_id = annotation['category_id']
        if categories[cat_id] not in class_labelling_scheme:
            continue
        category = categories[cat_id]

        regions = []
        for seg in annotation['segmentation']:
            points = []
            for i in range(0, len(seg), 2):
                points.append({
                    'x': seg[i],
                    'y': seg[i+1]
                })
            regions.append(points)


        labels.append({
            'label_type': 'polygon',
            'label_class': category,
            'source': source,
            'anno_data': {},
            'regions': regions,
            'object_id': str(uuid.uuid4())
        })
    
    return json.dumps(labels, indent=4)
