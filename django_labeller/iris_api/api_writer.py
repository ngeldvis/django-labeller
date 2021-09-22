import requests

class BaseAPIWriter():

    def __init__(self, url):
        self.url = url

    def get_items(self, params=None):
        return requests.get(self.url, params)

    def get_item(self, id):
        return requests.get(self.url+str(id)+'/')

    def save_item(self, data):
        return requests.post(self.url, json=data)

    def update_item(self, id, data):
        return requests.put(self.url+str(id)+'/', json=data)

    def delete_item(self, id):
        return requests.delete(self.url+str(id)+'/')


class ReadingAPIWriter(BaseAPIWriter):

    def __init__(self, url, token, bucket, org):
        self.url = '{base_url}{token}/{bucket}/{org}/'.format(
            base_url=url,
            token=token,
            bucket=bucket,
            org=org
        )

    def delete_measurements(self, measurement, params):
        return requests.delete(self.url, params=params)


class PhotoAPIWriter(BaseAPIWriter):

    def save_item(self, data, photo_path):
        with open(photo_path, 'rb') as f:
            return requests.post(self.url, data=data, files={'image': f})

    def update_item(self, id, data, photo_path):
        with open(photo_path, 'rb') as f:
            return requests.put(self.url+str(id)+'/', data=data, files = {'image': f})
