import os
import sys
import django
import logging

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client

logger = logging.getLogger(__name__)
c = Client()
try:
    logger.info("Requesting / ...")
    r = c.get('/')
    logger.info("Status: %s", r.status_code)
    if r.status_code != 200:
        logger.warning(r.content.decode('utf-8')[:2000])  # first 2k chars
except Exception:
    logger.exception("Error while requesting site root")
