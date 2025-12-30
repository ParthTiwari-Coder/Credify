"""Utility modules for fact-checking system"""

from .gemini_client import GeminiClient
from .embedding_utils import calculate_cosine_similarity, find_most_similar

__all__ = ['GeminiClient', 'calculate_cosine_similarity', 'find_most_similar']
