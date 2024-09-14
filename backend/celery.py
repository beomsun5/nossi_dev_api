from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from dotenv import read_dotenv  # Import this to load .env file
from pathlib import Path

# Load the .env file explicitly for Celery
env_path = Path('/workspace/backend/.env')
read_dotenv(dotenv=env_path)  # Add this to load .env file

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))