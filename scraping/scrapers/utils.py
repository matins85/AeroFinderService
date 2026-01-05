import re


def extract_airport_code(text):
    """Extract airport code from text like 'Lagos (LOS)'"""
    match = re.findall(r'\(([^)]+)\)', text)
    if match:
        return match[-1].upper()
    return ''

