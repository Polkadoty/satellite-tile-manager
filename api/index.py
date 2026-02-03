"""Vercel serverless entry point for the Satellite Tile Manager API."""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment to serverless before importing app
os.environ["ENVIRONMENT"] = "vercel"
os.environ["VERCEL"] = "1"

from src.api.app import app

# Export app directly for Vercel's ASGI handler
app = app
