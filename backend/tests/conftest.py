"""Pytest config for backend tests."""
import os

# Set env defaults so module import doesn't explode
os.environ.setdefault("GRAB_MAPS_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
