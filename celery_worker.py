from app import create_app, celery

app = create_app(for_worker=True)
app.app_context().push()