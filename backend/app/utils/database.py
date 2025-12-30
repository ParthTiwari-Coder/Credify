"""
Database models and connection for media analysis features
PostgreSQL database for storing perceptual hashes and reverse search results
"""

import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)


class Database:
    """
    PostgreSQL database connection pool and operations
    """
    
    def __init__(self):
        """Initialize database connection pool"""
        self.pool: Optional[SimpleConnectionPool] = None
        self._init_pool()
        self._create_tables()
    
    def _init_pool(self):
        """Initialize connection pool from environment variables"""
        try:
            db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'factcheck'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', 'postgres'),
                'minconn': 1,
                'maxconn': 10
            }
            
            self.pool = SimpleConnectionPool(**db_config)
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            # Fallback: allow system to work without database (feature flag can disable)
            self.pool = None
    
    def _create_tables(self):
        """Create required tables if they don't exist"""
        if not self.pool:
            logger.warning("Database pool not available, skipping table creation")
            return
        
        create_hashes_table = """
        CREATE TABLE IF NOT EXISTS media_hashes (
            id SERIAL PRIMARY KEY,
            hash_value VARCHAR(64) NOT NULL,
            media_type VARCHAR(20) NOT NULL,
            media_path TEXT,
            session_id VARCHAR(255),
            platform VARCHAR(100),
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            seen_count INTEGER DEFAULT 1,
            platforms_seen TEXT[],  -- Array of platform names
            UNIQUE(hash_value, media_type)
        );
        CREATE INDEX IF NOT EXISTS idx_hash_value ON media_hashes(hash_value);
        CREATE INDEX IF NOT EXISTS idx_session_id ON media_hashes(session_id);
        """
        
        create_reverse_search_table = """
        CREATE TABLE IF NOT EXISTS reverse_search_results (
            id SERIAL PRIMARY KEY,
            hash_value VARCHAR(64) NOT NULL,
            media_path TEXT,
            session_id VARCHAR(255),
            search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            oldest_known_use DATE,
            matched_sources JSONB,  -- Array of matched sources
            context_mismatch BOOLEAN DEFAULT FALSE,
            UNIQUE(hash_value, session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_reverse_hash ON reverse_search_results(hash_value);
        CREATE INDEX IF NOT EXISTS idx_reverse_session ON reverse_search_results(session_id);
        """
        
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor()
            cursor.execute(create_hashes_table)
            cursor.execute(create_reverse_search_table)
            conn.commit()
            cursor.close()
            self.pool.putconn(conn)
            logger.info("Database tables created/verified successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
    
    def get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            return None
        return self.pool.getconn()
    
    def put_connection(self, conn):
        """Return a connection to the pool"""
        if self.pool and conn:
            self.pool.putconn(conn)
    
    def store_hash(self, hash_value: str, media_type: str, media_path: str, 
                   session_id: str, platform: Optional[str] = None) -> bool:
        """
        Store or update a media hash
        
        Args:
            hash_value: Perceptual hash string
            media_type: 'image' or 'video'
            media_path: Path to media file
            session_id: Current session ID
            platform: Platform name (e.g., 'instagram', 'facebook')
            
        Returns:
            True if stored successfully
        """
        if not self.pool:
            return False
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Check if hash exists
            cursor.execute(
                "SELECT id, seen_count, platforms_seen FROM media_hashes WHERE hash_value = %s AND media_type = %s",
                (hash_value, media_type)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record
                hash_id, seen_count, platforms_seen = existing
                platforms_list = platforms_seen or []
                if platform and platform not in platforms_list:
                    platforms_list.append(platform)
                
                cursor.execute(
                    """
                    UPDATE media_hashes 
                    SET last_seen = CURRENT_TIMESTAMP, 
                        seen_count = seen_count + 1,
                        platforms_seen = %s
                    WHERE id = %s
                    """,
                    (platforms_list, hash_id)
                )
            else:
                # Insert new record
                platforms_list = [platform] if platform else []
                cursor.execute(
                    """
                    INSERT INTO media_hashes 
                    (hash_value, media_type, media_path, session_id, platform, platforms_seen)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (hash_value, media_type, media_path, session_id, platform, platforms_list)
                )
            
            conn.commit()
            cursor.close()
            self.put_connection(conn)
            return True
        except Exception as e:
            logger.error(f"Failed to store hash: {e}")
            if conn:
                conn.rollback()
                self.put_connection(conn)
            return False
    
    def find_similar_hashes(self, hash_value: str, media_type: str, 
                            threshold: int = 5) -> List[Dict]:
        """
        Find similar hashes using Hamming distance
        
        Args:
            hash_value: Hash to search for
            media_type: 'image' or 'video'
            threshold: Maximum Hamming distance (default 5)
            
        Returns:
            List of matching hash records
        """
        if not self.pool:
            return []
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get all hashes of the same type
            cursor.execute(
                "SELECT * FROM media_hashes WHERE media_type = %s",
                (media_type,)
            )
            all_hashes = cursor.fetchall()
            
            # Calculate Hamming distance for each
            matches = []
            for record in all_hashes:
                stored_hash = record['hash_value']
                distance = self._hamming_distance(hash_value, stored_hash)
                if distance <= threshold:
                    record_dict = dict(record)
                    record_dict['similarity_score'] = 1.0 - (distance / len(hash_value))
                    record_dict['hamming_distance'] = distance
                    matches.append(record_dict)
            
            cursor.close()
            self.put_connection(conn)
            return matches
        except Exception as e:
            logger.error(f"Failed to find similar hashes: {e}")
            if conn:
                self.put_connection(conn)
            return []
    
    def store_reverse_search_result(self, hash_value: str, media_path: str, 
                                   session_id: str, oldest_known_use: Optional[str],
                                   matched_sources: List[Dict], 
                                   context_mismatch: bool) -> bool:
        """
        Store reverse search results
        
        Args:
            hash_value: Perceptual hash of the media
            media_path: Path to media file
            session_id: Current session ID
            oldest_known_use: Earliest date found (YYYY-MM-DD format)
            matched_sources: List of matched source dictionaries
            context_mismatch: Whether context differs from current usage
            
        Returns:
            True if stored successfully
        """
        if not self.pool:
            return False
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO reverse_search_results 
                (hash_value, media_path, session_id, oldest_known_use, matched_sources, context_mismatch)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (hash_value, session_id) DO UPDATE SET
                    search_timestamp = CURRENT_TIMESTAMP,
                    oldest_known_use = EXCLUDED.oldest_known_use,
                    matched_sources = EXCLUDED.matched_sources,
                    context_mismatch = EXCLUDED.context_mismatch
                """,
                (hash_value, media_path, session_id, oldest_known_use, 
                 matched_sources, context_mismatch)
            )
            
            conn.commit()
            cursor.close()
            self.put_connection(conn)
            return True
        except Exception as e:
            logger.error(f"Failed to store reverse search result: {e}")
            if conn:
                conn.rollback()
                self.put_connection(conn)
            return False
    
    @staticmethod
    def _hamming_distance(hash1: str, hash2: str) -> int:
        """Calculate Hamming distance between two hash strings"""
        if len(hash1) != len(hash2):
            return max(len(hash1), len(hash2))
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
    
    def close(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")

