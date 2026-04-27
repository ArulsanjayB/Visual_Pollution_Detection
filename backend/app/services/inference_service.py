"""
Inference service — singleton wrapper loaded once at app startup.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ml'))

from inference import PollutionInferenceEngine


class InferenceService(PollutionInferenceEngine):
    """Thin wrapper — loaded once in app lifespan, shared across requests."""
    pass
