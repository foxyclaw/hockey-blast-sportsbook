"""
Re-export PredBase so models can import from a stable location.
"""
from app.db import PredBase

__all__ = ["PredBase"]
