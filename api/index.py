"""Vercel serverless entry point for the Satellite Tile Manager API."""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import app

# Vercel expects a handler or the app directly
handler = app
