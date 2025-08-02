"""
RAG Service with lazy loading to avoid import errors during app startup
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

class RAGService:
    """Service for RAG (Retrieval Augmented Generation) operations with lazy loading"""
    
    def __init__(self):
        self._sentence_transformer = None
        self._annoy_index = None
        self._tiktoken_encoder = None
        self._initialized = False
        self._metrics = defaultdict(int)
        self._last_health_check = None
        self._embeddings_list = []  # Store embeddings for annoy index
        
        # Environment variable configuration
        self.enabled = os.environ.get('ENABLE_RAG', 'true').lower() == 'true'
        self.model_name = os.environ.get('RAG_MODEL', 'all-MiniLM-L6-v2')
        self.max_tokens = int(os.environ.get('RAG_MAX_TOKENS', '500'))
        self.chunk_overlap = int(os.environ.get('RAG_CHUNK_OVERLAP', '50'))
        
        logger.info(f"RAG Service initialized - Enabled: {self.enabled}, Model: {self.model_name}")
    
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
            self._annoy_index = AnnoyIndex(dimension, 'angular')  # Use angular distance for cosine similarity
            
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
        try:
            chunks = RAGChunk.query.filter(RAGChunk.embedding.isnot(None)).all()
            if chunks:
                embeddings = []
                for chunk in chunks:
                    # Convert stored embedding back to numpy array
                    embedding = np.frombuffer(chunk.embedding, dtype=np.float32)
                    embeddings.append(embedding)
                
                if embeddings:
                    self._embeddings_list = embeddings
                    # Build Annoy index
                    for i, embedding in enumerate(embeddings):
                        self._annoy_index.add_item(i, embedding.tolist())
                    
                    # Build the index
                    self._annoy_index.build(10)  # 10 trees for good accuracy
                    logger.info(f"Loaded {len(embeddings)} existing embeddings into Annoy index")
                    
        except Exception as e:
            logger.error(f"Error loading existing embeddings: {e}")
    
    def chunk_text(self, text: str, max_tokens: int = None, overlap: int = None) -> List[str]:
        """Split text into chunks with token-aware splitting"""
        max_tokens = max_tokens or self.max_tokens
        overlap = overlap or self.chunk_overlap
        
        if not self._lazy_init():
            # Fallback to simple character-based chunking
            chunk_size = max_tokens * 4  # Rough approximation
            chunks = []
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size]
                if chunk.strip():
                    chunks.append(chunk.strip())
            
            self._metrics['chunks_created'] += len(chunks)
            return chunks
        
        try:
            # Token-aware chunking
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
            # Fallback to simple splitting
            fallback_chunks = [text[i:i+2000] for i in range(0, len(text), 1500)]
            self._metrics['chunks_created'] += len(fallback_chunks)
            return fallback_chunks
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text"""
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
        if not self._lazy_init():
            logger.warning("RAG service not available - storing chunks without embeddings")
            
        try:
            # Delete existing chunks for this document
            RAGChunk.query.filter_by(document_id=document_id).delete()
            
            chunk_objects = []
            embeddings_to_add = []
            
            for i, chunk_text in enumerate(chunks):
                # Generate embedding if RAG is available
                embedding = None
                embedding_bytes = None
                
                if self._initialized:
                    embedding = self.generate_embedding(chunk_text)
                    if embedding is not None:
                        embedding_bytes = embedding.tobytes()
                        embeddings_to_add.append(embedding)
                
                # Create chunk object
                chunk = RAGChunk(
                    document_id=document_id,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    embedding=embedding_bytes
                )
                chunk_objects.append(chunk)
            
            # Save to database
            db.session.bulk_save_objects(chunk_objects)
            db.session.commit()
            
            # Add to Annoy index if embeddings were generated
            if embeddings_to_add and self._initialized:
                start_index = len(self._embeddings_list)
                for i, embedding in enumerate(embeddings_to_add):
                    self._annoy_index.add_item(start_index + i, embedding.tolist())
                    self._embeddings_list.append(embedding)
                
                # Rebuild the index
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
        if not self._lazy_init():
            logger.warning("RAG service not available - falling back to text search")
            return self._fallback_text_search(query, top_k)
        
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                return self._fallback_text_search(query, top_k)
            
            # Search Annoy index
            indices = self._annoy_index.get_nns_by_vector(query_embedding.tolist(), top_k, include_distances=True)
            chunk_indices, distances = indices
            
            # Get corresponding chunks from database
            results = []
            chunks = RAGChunk.query.filter(RAGChunk.embedding.isnot(None)).all()
            
            for i, (idx, distance) in enumerate(zip(chunk_indices, distances)):
                if idx < len(chunks):
                    chunk = chunks[idx]
                    # Convert distance to similarity score (1 - normalized distance)
                    similarity_score = 1.0 - (distance / np.sqrt(len(query_embedding)))
                    results.append({
                        'chunk_id': chunk.id,
                        'document_id': chunk.document_id,
                        'chunk_text': chunk.chunk_text,
                        'similarity_score': float(similarity_score),
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
            # Simple text search using PostgreSQL's text search
            chunks = RAGChunk.query.filter(
                RAGChunk.chunk_text.ilike(f'%{query}%')
            ).limit(top_k).all()
            
            results = []
            for chunk in chunks:
                results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'chunk_text': chunk.chunk_text,
                    'similarity_score': 0.5,  # Default score for text match
                    'chunk_index': chunk.chunk_index
                })
            
            self._metrics['queries_processed'] += 1
            return results
            
        except Exception as e:
            logger.error(f"Error in fallback text search: {e}")
            return []
    
    def save_query(self, query_text: str, results: List[Dict[str, Any]], user_id: Optional[int] = None) -> Optional[int]:
        """Save query and results for analytics"""
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
        self._last_health_check = time.time()
        return self._lazy_init()

# Global instance
rag_service = RAGService() 