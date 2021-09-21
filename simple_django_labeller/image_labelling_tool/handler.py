import json

from image_labelling_tool import labelled_image

class DatabaseHandler:

    def __init__(self, images) -> None:
        self.images = images

    def get_labelled_image(self, image):
        image_src = labelled_image.InMemoryImageSourceAlt(
            None, image.get_name(), image.height, image.width)
        labels_json = image.labels.labels_json_str
        labels_store = labelled_image.InMemoryLabelsStore.from_json(json.loads(labels_json))
        return labelled_image.LabelledImage(image_src, labels_store)

    def get_labelled_images(self):
        return [self.get_labelled_image(image) for image in self.images]
