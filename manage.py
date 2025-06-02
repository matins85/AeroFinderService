#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from dotenv import load_dotenv


def main():
    """Run administrative tasks."""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_path = os.path.join(BASE_DIR, '.env')

    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    else:
        load_dotenv()  # fallback (if .env is elsewhere in the system)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aerofinder.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
