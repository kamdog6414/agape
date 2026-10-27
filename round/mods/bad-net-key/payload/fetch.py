"""Deliberately bad fixture: network import plus a fake secret-looking line."""
from urllib.request import urlopen

API_KEY = "FAKE-DEMO-VALUE-0000-not-real"


def run(request):
    return {"text": urlopen("http://example.invalid/").read().decode()}
