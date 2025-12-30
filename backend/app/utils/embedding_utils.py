"""
Embedding utilities for semantic similarity detection
Uses Gemini embeddings exclusively
"""

import logging
import numpy as np
from typing import List
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


def calculate_cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        Similarity score between 0 and 1
    """
    if not embedding1 or not embedding2:
        return 0.0
    
    try:
        # Convert to numpy arrays
        vec1 = np.array(embedding1).reshape(1, -1)
        vec2 = np.array(embedding2).reshape(1, -1)
        
        # Calculate cosine similarity
        similarity = cosine_similarity(vec1, vec2)[0][0]
        
        return float(similarity)
    except Exception as e:
        logger.error(f"Cosine similarity calculation failed: {e}")
        return 0.0


def find_most_similar(
    query_embedding: List[float],
    candidate_embeddings: List[List[float]],
    threshold: float = 0.85
) -> List[tuple]:
    """
    Find most similar embeddings above threshold
    
    Args:
        query_embedding: Query embedding vector
        candidate_embeddings: List of candidate embedding vectors
        threshold: Minimum similarity threshold
        
    Returns:
        List of (index, similarity_score) tuples for matches above threshold
    """
    matches = []
    
    for idx, candidate in enumerate(candidate_embeddings):
        similarity = calculate_cosine_similarity(query_embedding, candidate)
        if similarity >= threshold:
            matches.append((idx, similarity))
    
    # Sort by similarity (highest first)
    matches.sort(key=lambda x: x[1], reverse=True)
    
    return matches
