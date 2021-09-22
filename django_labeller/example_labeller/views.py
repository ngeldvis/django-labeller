import os, datetime, json, tempfile, zipfile
import celery.result
import json
import urllib.request

from PIL import Image
from io import BytesIO

from dateutil.tz import tzlocal

from django.http import HttpResponse
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie

from django.conf import settings
import django.utils.timezone

from image_labelling_tool import models as lt_models
from image_labelling_tool import labelling_tool
from image_labelling_tool import django2coco, handler
from image_labelling_tool import labelling_tool_views, schema_editor_views, labelled_image

from . import models, tasks, forms

from iris_api.api_writer import BaseAPIWriter
from iris_api.constants import PHOTOS_URL, PHOTO_ANNOTATIONS_URL

@ensure_csrf_cookie
def home(request):
    upload_form = forms.ImageUploadForm()

    if 'example_labeller_message' in request.session:
        message = request.session.pop('example_labeller_message')
    else:
        message = None

    context = {
        'upload_form': upload_form,
        'message': message,
        'num_images': len(models.ImageWithLabels.objects.all())
    }
    return render(request, 'index.html', context)


@ensure_csrf_cookie
def upload_images(request):
    if request.method == 'POST':
        upload_form = forms.ImageUploadForm(request.POST, request.FILES)

        if upload_form.is_valid():
            uploaded_file = upload_form.cleaned_data['file']

            print(uploaded_file.content_type)

            if uploaded_file.content_type in {'image/jpeg', 'image/png'}:
                # Single image upload

                # Blank labels
                labels_model = lt_models.Labels(creation_date=datetime.date.today())
                labels_model.save()

                image_model = models.ImageWithLabels(labels=labels_model)
                image_model.image.save(os.path.basename(uploaded_file.name), uploaded_file)
                image_model.save()
            elif uploaded_file.content_type in {'application/zip', 'application/x-zip-compressed'}:
                # ZIP file

                # Write to a temporary file
                handle, upload_path =tempfile.mkstemp()
                os.close(handle)
                os.remove(upload_path)

                with open(upload_path, 'wb+') as f_dest:
                    for chunk in uploaded_file.chunks():
                        f_dest.write(chunk)

                # Load the ZIP and get its contents
                z = zipfile.ZipFile(upload_path, 'r')

                # Pair image files with corresponding label files
                name_to_image_and_labels = {}
                for filename_and_ext in z.namelist():
                    filename, ext = os.path.splitext(filename_and_ext)
                    if ext.lower() in {'.png', '.jpg', '.jpeg'}:
                        entry = name_to_image_and_labels.setdefault(filename, dict(image=None, labels=None))
                        entry['image'] = filename_and_ext
                    elif ext.lower() == '.json':
                        if filename.endswith('__labels'):
                            filename = filename[:-8]
                        entry = name_to_image_and_labels.setdefault(filename, dict(image=None, labels=None))
                        entry['labels'] = filename_and_ext

                # Add all images using a single transaction
                with transaction.atomic():
                    for name, entry in name_to_image_and_labels.items():
                        # Entry is only valid if there is an image file
                        if entry['image'] is not None:
                            valid_image = False
                            # Attempt to open the image to ensure its valid
                            with z.open(entry['image'], mode='r') as f_img:
                                try:
                                    im = Image.open(f_img)
                                except IOError:
                                    pass
                                else:
                                    valid_image = True
                                    im.close()

                            if valid_image:
                                labels_model = None
                                # See if we have a labels file
                                if entry['labels'] is not None:
                                    # Open the labels
                                    with z.open(entry['labels'], mode='r') as f_labels:
                                        try:
                                            wrapped_labels = json.load(f_labels)
                                        except IOError:
                                            pass
                                        else:
                                            # Get the modification date and time of the labels file
                                            z_info = z.getinfo(entry['labels'])
                                            year, month, day, hour, minute, second = z_info.date_time
                                            creation_date = datetime.date(
                                                year=year, month=month, day=day)
                                            modification_datetime = datetime.datetime(
                                                year=year, month=month, day=day, hour=hour, minute=minute,
                                                second=second, tzinfo=tzlocal())
                                            if request.user.is_authenticated:
                                                modification_user = request.user
                                            else:
                                                modification_user = None

                                            # Unwrap the labels
                                            labels, complete = labelling_tool.PersistentLabelledImage._unwrap_labels(
                                                wrapped_labels)
                                            complete = complete if isinstance(complete, bool) else False

                                            # Build labels model
                                            labels_model = lt_models.Labels(
                                                labels_json_str=json.dumps(labels), complete=complete,
                                                creation_date=creation_date,
                                                last_modified_datetime=modification_datetime,
                                                last_modified_by=modification_user)
                                            labels_model.save()

                                if labels_model is None:
                                    # No labels loaded; create an empty labels model
                                    labels_model = lt_models.Labels(creation_date=datetime.date.today())
                                    labels_model.save()

                                image_model = models.ImageWithLabels(labels=labels_model)
                                image_model.image.save(os.path.basename(entry['image']),
                                                       File(z.open(entry['image'], mode='r')))
                                image_model.save()
            else:
                # Unknown type; put message in session
                request.session['example_labeller_message'] = 'unknown_upload_filetype'
    return redirect('example_labeller:home')


@ensure_csrf_cookie
def upload_images_db(request):

    photos_api_writer = BaseAPIWriter(PHOTOS_URL)
    response = photos_api_writer.get_items()
    images = json.loads(response.text)['results']

    for i in images:

        image_id = i['id']
        
        try:
            models.ImageWithLabels.objects.get(pk=image_id)

        except models.ImageWithLabels.DoesNotExist:
            labels_model = lt_models.Labels(creation_date=datetime.date.today())
            labels_model.save()

            image_path, _ = urllib.request.urlretrieve(i['image'])
            image = Image.open(image_path)

            image_model = models.ImageWithLabels(labels=labels_model)
            image_model.url, image_model.id = i['image'], image_id
            image_model.width, image_model.height = image.size
            image_model.save()
            
            os.remove(image_path)

    return redirect('example_labeller:home')


def annotate_image(request, image_id):

    # 1. get temporary image file and send api request to get annotations
    image_annotation_api_writer = BaseAPIWriter(PHOTO_ANNOTATIONS_URL)
    response = image_annotation_api_writer.get_item(str(image_id))
    coco_str = json.dumps(json.loads(response.text)['annotation_json'])

    # 2. convert coco format to local json data format
    scheme = lt_models.LabelClass.objects.all()
    class_labelling_scheme = {class_.name: class_.id for class_ in scheme}

    labels_json_str = django2coco.coco2django(coco_str, class_labelling_scheme, 'annotations api')
    labels_json = json.loads(labels_json_str)

    # labels_json_str = '[{"label_type": "polygon", "label_class": "lake", "source": "manual", "anno_data": {}, "regions": [[{"x": 32.40825241055651, "y": 30.7411293971059}, {"x": 32.40825241055651, "y": 179.9083305380065}, {"x": 162.2030897669246, "y": 30.7411293971059}]], "object_id": "e39730fe-9e94-4e93-9782-147fec51304e__2"}]'
    # labels_json = json.loads(labels_json_str)

    # 3. get image labels to update
    img = get_object_or_404(models.ImageWithLabels, id=int(image_id))
    img_labels = img.labels

    # 4. add the new labels to the current images labels
    cur_labels_json = json.loads(img_labels.labels_json_str)
    for label in labels_json:
        cur_labels_json.append(label)
    
    # 5. save the labels object
    img_labels.labels_json_str = json.dumps(cur_labels_json)
    img_labels.save()

    # 6. make sure to delete temporary file if necessary

    image = get_object_or_404(models.ImageWithLabels, id=int(image_id))
    # print(image.labels)

    return HttpResponse('successful', status=200)


@ensure_csrf_cookie
def gallery(request):
    context = {
        'images': [
            {'url': img.url, 'id': img.id} for img in models.ImageWithLabels.objects.all()
        ]
    }
    return render(request, 'gallery.html', context)

@ensure_csrf_cookie
def tool(request):
    image_descriptors = [
        labelling_tool.image_descriptor(
            image_id=img.id, url=img.url,
            width=img.width, height=img.height
        ) for img in models.ImageWithLabels.objects.all()
    ]

    try:
        schema = lt_models.LabellingSchema.objects.get(name='default')
    except lt_models.LabellingSchema.DoesNotExist:
        schema_js = dict(colour_schemes=[], label_class_groups=[])
    else:
        schema_js = schema.json_for_tool()

    context = {
        'labelling_schema': schema_js,
        'image_descriptors': image_descriptors,
        'initial_image_id': str(models.ImageWithLabels.objects.all()[0].id) if 'image_id' not in request.GET else request.GET['image_id'],
        'labelling_tool_config': settings.LABELLING_TOOL_CONFIG,
        'tasks': lt_models.LabellingTask.objects.filter(enabled=True).order_by('order_key'),
        'anno_controls': [c.to_json() for c in settings.ANNO_CONTROLS],
        'enable_locking': settings.LABELLING_TOOL_ENABLE_LOCKING,
        'dextr_available': settings.LABELLING_TOOL_DEXTR_AVAILABLE,
        'dextr_polling_interval': settings.LABELLING_TOOL_DEXTR_POLLING_INTERVAL,
    }
    return render(request, 'tool.html', context)


class LabellingToolAPI (labelling_tool_views.LabellingToolViewWithLocking):

    def get_image(self, image_id_str, *args, **kwargs):
        image = get_object_or_404(models.ImageWithLabels, id=int(image_id_str))
        return image

    def get_labels(self, request, image_id_str, *args, **kwargs):
        image = get_object_or_404(models.ImageWithLabels, id=int(image_id_str))
        return image.labels

    def get_unlocked_image_id(self, request, image_ids, *args, **kwargs):
        unlocked_labels = lt_models.Labels.objects.unlocked()
        unlocked_q = Q(id__in=image_ids, labels__in=unlocked_labels)
        # TODO FOR YOUR APPLICATION
        # filter images for those accessible to the user to guard against maliciously crafted requests
        accessible_q = Q()
        unlocked_imgs = models.ImageWithLabels.objects.filter(unlocked_q & accessible_q).distinct()
        first_unlocked = unlocked_imgs.first()
        return first_unlocked.id if first_unlocked is not None else None

    def dextr_request(self, request, image_id_str, dextr_id, dextr_points):
        """
        :param request: HTTP request
        :param image_id_str: image ID that identifies the image that we are labelling
        :param dextr_id: an ID number the identifies the DEXTR request
        :param dextr_points: the 4 points as a list of 2D vectors ({'x': <x>, 'y': <y>}) in the order
            top edge, left edge, bottom edge, right edge
        :return: contours/regions a list of lists of 2D vectors, each of which is {'x': <x>, 'y': <y>}
        """
        if settings.LABELLING_TOOL_DEXTR_AVAILABLE:
            image = get_object_or_404(models.ImageWithLabels, id=int(image_id_str))
            cel_result = tasks.dextr.delay(image.url, dextr_points)
            dtask = models.DextrTask(
                image=image, 
                image_id_str=image_id_str, 
                dextr_id=dextr_id, 
                celery_task_id=cel_result.id
            )
            dtask.save()
        return None

    def dextr_poll(self, request, image_id_str, dextr_ids):
        """
        :param request: HTTP request
        :param image_id_str: image ID that identifies the image that we are labelling
        :param dextr_ids: The DEXTR request IDs that the client is interested in
        :return: a list of dicts where each dict takes the form:
            {
                'image_id': image ID string that identifies the image that the label applies to
                'dextr_id': the ID number that identifies the dextr job/request
                'regions': contours/regions a list of lists of 2D vectors, each of which is {'x': <x>, 'y': <y>}
            }
        """
        to_remove = []
        dextr_labels = []
        for dtask in models.DextrTask.objects.filter(image__id=image_id_str, dextr_id__in=dextr_ids):
            uuid = dtask.celery_task_id
            res = celery.result.AsyncResult(uuid)
            if res.ready():
                try:
                    regions = res.get()
                except:
                    # An error occurred during the DEXTR task; nothing we can do
                    pass
                else:
                    dextr_label = dict(image_id=dtask.image_id_str, dextr_id=dtask.dextr_id, regions=regions)
                    dextr_labels.append(dextr_label)
                to_remove.append(dtask)

        # Remove old tasks
        oldest = django.utils.timezone.now() - datetime.timedelta(minutes=10)
        for old_task in models.DextrTask.objects.filter(creation_timestamp__lt=oldest):
            to_remove.append(old_task)

        for r in to_remove:
            r.delete()

        return dextr_labels


@ensure_csrf_cookie
def schema_editor(request):
    context = {'schema': lt_models.LabellingSchema.objects.get(name='default')}
    return render(request, 'schema_editor.html', context)


class SchemaEditorAPI (schema_editor_views.SchemaEditorView):
    def get_schema(self, request, *args, **kwargs):
        return lt_models.LabellingSchema.objects.get(name='default')


@ensure_csrf_cookie
def test_button(request):
    print('-------------------------------------')

    print(PHOTO_ANNOTATIONS_URL)

    # scheme = lt_models.LabelClass.objects.all()
    # class_labbelling_scheme = {class_.name: class_.id for class_ in scheme}

    # print(class_labbelling_scheme)

    # ds_info = {
    #     "description": "ECOATION GREENHOUSE IMAGE LABEL DATASET",
    #     "url": "",
    #     "version": "0.0.1",
    #     "year": datetime.datetime.now().year,
    #     "contributor": "",
    #     "date_created": datetime.datetime.now().isoformat(),
    # }

    # img = get_object_or_404(models.ImageWithLabels, id=50)

    # db_handler = handler.DatabaseHandler([img])
    # labelled_images = db_handler.get_labelled_images()

    # # print(labelled_images)

    # coco = django2coco.django2coco(labelled_images, class_labbelling_scheme, ds_info)

    # print(coco)

    print('-------------------------------------')
    return redirect('example_labeller:home')
