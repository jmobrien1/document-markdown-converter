"""
RAG Service with complete isolation - can be disabled entirely via environment variable
"""
import logging
import os
import time
from typing import List, Dict, Optional, Any
from collections import defaultdict
import numpy as np
from sqlalchemy.exc import SQLAlchemyError
from app.models import RAGChunk, RAGQuery, db

logger = logging.getLogger(__name__)

# Global flag to completely disable RAG functionality
RAG_ENABLED = os.environ.get('ENABLE_RAG', 'false').lower() == 'true'

class RAGService:
    """Service for RAG (Retrieval Augmented Generation) operations"""
    
    def __init__(self):
        self._sentence_transformer = None
        self._annoy_index = None
        self._tiktoken_encoder = None
        self._initialized = False
        self._metrics = defaultdict(int)
        self._last_health_check = None
        self._embeddings_list = []
        
        # Environment variable configuration
        self.enabled = RAG_ENABLED
        self.model_name = os.environ.get('RAG_MODEL', 'all-MiniLM-L6-v2')
        self.max_tokens = int(os.environ.get('RAG_MAX_TOKENS', '500'))
        self.chunk_overlap = int(os.environ.get('RAG_CHUNK_OVERLAP', '50'))
        
        logger.info(f"RAG Service initialized - Enabled: {self.enabled}, Model: {self.model_name}")
        
        # DO NOT initialize anything here - wait until first use
    
    def _lazy_init(self):
        """Initialize heavy dependencies only when needed"""
        if self._initialized:
            return True
            
        if not self.enabled:
            logger.info("RAG service is disabled via ENABLE_RAG environment variable")
            return False
            
        try:
            # Import heavy dependencies only when needed
            import tiktoken
            from annoy import AnnoyIndex
            from sentence_transformers import SentenceTransformer
            
            # Initialize components
            self._tiktoken_encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")
            self._sentence_transformer = SentenceTransformer(self.model_name)
            
            # Initialize Annoy index
            dimension = 384  # all-MiniLM-L6-v2 embedding dimension
            self._annoy_index = AnnoyIndex(dimension, 'angular')
            
            # Load existing embeddings if any
            self._load_existing_embeddings()
            
            self._initialized = True
            self._metrics['initializations'] += 1
            logger.info("RAG service initialized successfully")
            return True
            
        except ImportError as e:
            logger.error(f"Failed to import RAG dependencies: {e}")
            self._metrics['import_errors'] += 1
            return False
        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
            self._metrics['init_errors'] += 1
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics for monitoring"""
        return {
            'initializations': self._metrics['initializations'],
            'import_errors': self._metrics['import_errors'],
            'init_errors': self._metrics['init_errors'],
            'queries_processed': self._metrics['queries_processed'],
            'chunks_created': self._metrics['chunks_created'],
            'embeddings_generated': self._metrics['embeddings_generated'],
            'is_available': self.is_available(),
            'is_enabled': self.enabled,
            'model_name': self.model_name,
            'last_health_check': self._last_health_check
        }
    
    def _load_existing_embeddings(self):
        """Load existing embeddings into Annoy index"""
        if not self.enabled:
            return
            
        try:
            chunks = RAGChunk.query.filter(RAGChunk.embedding.isnot(None)).all()
            if chunks:
                embeddings = []
                for chunk in chunks:
                    embedding = np.frombuffer(chunk.embedding, dtype=np.float32)
                    embeddings.append(embedding)
                
                if embeddings:
                    self._embeddings_list = embeddings
                    for i, embedding in enumerate(embeddings):
                        self._annoy_index.add_item(i, embedding.tolist())
                    
                    self._annoy_index.build(10)
                    logger.info(f"Loaded {len(embeddings)} existing embeddings into Annoy index")
                    
        except Exception as e:
            logger.error(f"Error loading existing embeddings: {e}")
    
    def chunk_text(self, text: str, max_tokens: int = None, overlap: int = None) -> List[str]:
        """Split text into chunks with token-aware splitting"""
        if not self.enabled:
            return []
            
        max_tokens = max_tokens or self.max_tokens
        overlap = overlap or self.chunk_overlap
        
        # Try lazy initialization
        if not self._lazy_init():
            # Fallback to simple character-based chunking
            chunk_size = max_tokens * 4
            chunks = []
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size]
                if chunk.strip():
                    chunks.append(chunk.strip())
            
            self._metrics['chunks_created'] += len(chunks)
            return chunks
        
        try:
            tokens = self._tiktoken_encoder.encode(text)
            chunks = []
            
            for i in range(0, len(tokens), max_tokens - overlap):
                chunk_tokens = tokens[i:i + max_tokens]
                chunk_text = self._tiktoken_encoder.decode(chunk_tokens)
                if chunk_text.strip():
                    chunks.append(chunk_text.strip())
            
            self._metrics['chunks_created'] += len(chunks)
            return chunks
            
        except Exception as e:
            logger.error(f"Error in chunk_text: {e}")
            fallback_chunks = [text[i:i+2000] for i in range(0, len(text), 1500)]
            self._metrics['chunks_created'] += len(fallback_chunks)
            return fallback_chunks
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text"""
        if not self.enabled:
            return None
            
        # Try lazy initialization
        if not self._lazy_init():
            return None
            
        try:
            embedding = self._sentence_transformer.encode(text, convert_to_numpy=True)
            self._metrics['embeddings_generated'] += 1
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def store_document_chunks(self, document_id: int, chunks: List[str]) -> bool:
        """Store document chunks with embeddings"""
        if not self.enabled:
            logger.warning("RAG service is disabled - not storing chunks")
            return False
            
        try:
            RAGChunk.query.filter_by(document_id=document_id).delete()
            
            chunk_objects = []
            embeddings_to_add = []
            
            # Try lazy initialization for embeddings
            can_generate_embeddings = self._lazy_init()
            
            for i, chunk_text in enumerate(chunks):
                embedding = None
                embedding_bytes = None
                
                if can_generate_embeddings:
                    embedding = self.generate_embedding(chunk_text)
                    if embedding is not None:
                        embedding_bytes = embedding.tobytes()
                        embeddings_to_add.append(embedding)
                
                chunk = RAGChunk(
                    document_id=document_id,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    embedding=embedding_bytes
                )
                chunk_objects.append(chunk)
            
            db.session.bulk_save_objects(chunk_objects)
            db.session.commit()
            
            if embeddings_to_add and can_generate_embeddings:
                start_index = len(self._embeddings_list)
                for i, embedding in enumerate(embeddings_to_add):
                    self._annoy_index.add_item(start_index + i, embedding.tolist())
                    self._embeddings_list.append(embedding)
                
                self._annoy_index.build(10)
            
            logger.info(f"Stored {len(chunks)} chunks for document {document_id}")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"Database error storing chunks: {e}")
            db.session.rollback()
            return False
        except Exception as e:
            logger.error(f"Error storing document chunks: {e}")
            return False
    
    def search_similar_chunks(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity"""
        if not self.enabled:
            logger.warning("RAG service is disabled - falling back to text search")
            return self._fallback_text_search(query, top_k)
            
        # Try lazy initialization
        if not self._lazy_init():
            logger.warning("RAG service not available - falling back to text search")
            return self._fallback_text_search(query, top_k)
            
        try:
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                return self._fallback_text_search(query, top_k)
            
            # Search Annoy index
            query_vector = query_embedding.tolist()
            indices = self._annoy_index.get_nns_by_vector(query_vector, top_k, include_distances=True)
            
            # Get corresponding chunks from database
            results = []
            chunks = RAGChunk.query.filter(RAGChunk.embedding.isnot(None)).all()
            
            for i, (idx, distance) in enumerate(zip(indices[0], indices[1])):
                if idx < len(chunks):
                    chunk = chunks[idx]
                    # Convert distance to similarity score (1 - distance)
                    similarity_score = 1.0 - (distance / 2.0)  # Normalize to 0-1
                    
                    results.append({
                        'chunk_id': chunk.id,
                        'document_id': chunk.document_id,
                        'chunk_text': chunk.chunk_text,
                        'similarity_score': similarity_score,
                        'chunk_index': chunk.chunk_index
                    })
            
            self._metrics['queries_processed'] += 1
            return results
            
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            return self._fallback_text_search(query, top_k)
    
    def _fallback_text_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Fallback text-based search when vector search is unavailable"""
        try:
            chunks = RAGChunk.query.filter(
                RAGChunk.chunk_text.ilike(f'%{query}%')
            ).limit(top_k).all()
            
            results = []
            for chunk in chunks:
                results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'chunk_text': chunk.chunk_text,
                    'similarity_score': 0.5,
                    'chunk_index': chunk.chunk_index
                })
            
            self._metrics['queries_processed'] += 1
            return results
            
        except Exception as e:
            logger.error(f"Error in fallback text search: {e}")
            return []
    
    def save_query(self, query_text: str, results: List[Dict[str, Any]], user_id: Optional[int] = None) -> Optional[int]:
        """Save query and results for analytics"""
        if not self.enabled:
            return None
            
        try:
            query_obj = RAGQuery(
                query_text=query_text,
                user_id=user_id,
                results_count=len(results)
            )
            
            db.session.add(query_obj)
            db.session.commit()
            
            logger.info(f"Saved RAG query: {query_text[:50]}...")
            return query_obj.id
            
        except SQLAlchemyError as e:
            logger.error(f"Error saving query: {e}")
            db.session.rollback()
            return None
    
    def is_available(self) -> bool:
        """Check if RAG service is fully available"""
        if not self.enabled:
            return False
            
        # Try lazy initialization
        return self._lazy_init()

# Create global instance only if RAG is enabled
if RAG_ENABLED:
    try:
        rag_service = RAGService()
    except Exception as e:
        logger.error(f"Failed to create RAG service: {e}")
        rag_service = None
else:
    rag_service = None

def get_rag_service():
    """Get RAG service instance - returns None if disabled"""
    return rag_service 