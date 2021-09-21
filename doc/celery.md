# Running the Celery worker for dextr

to do this all you should need to do is the following:

```bash
# cd into the right directory
cd simple_django_labeller
# run the celery worker
celery -A example_labeller_app worker -l info
```