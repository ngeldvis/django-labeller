from django.urls import include, path

from . import views

app_name = 'example_labeller'

urlpatterns = [
    path('', views.home, name='home'),
    path('upload_images', views.upload_images, name='upload_images'),
    path('upload_images_db', views.upload_images_db, name='upload_images_db'),
    path('tool', views.tool, name='tool'),
    path('gallery', views.gallery, name='gallery'),
    path('labelling_tool_api', views.LabellingToolAPI.as_view(), name='labelling_tool_api'),
    path('schema_editor', views.schema_editor, name='schema_editor'),
    path('schema_editor_api', views.SchemaEditorAPI.as_view(), name='schema_editor_api'),
    path('test_button', views.test_button, name='test_button'),
    path('annotate_image/<int:image_id>', views.annotate_image, name='annotate_image'),
]
