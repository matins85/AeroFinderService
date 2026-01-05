import re
import random
import time


def extract_airport_code(text):
    """Extract airport code from text like 'Lagos (LOS)'"""
    match = re.findall(r'\(([^)]+)\)', text)
    if match:
        return match[-1].upper()
    return ''


def wait(min_time=2, max_time=4):
    """Wait for a random amount of time between min_time and max_time"""
    time.sleep(random.uniform(min_time, max_time))

