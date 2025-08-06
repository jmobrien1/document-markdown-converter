"""
RAG Service with complete isolation - can be disabled entirely via environment variable
"""
import logging
import os
import time
import warnings
import json
from typing import List, Dict, Optional, Any
from collections import defaultdict
import numpy as np
from sqlalchemy.exc import SQLAlchemyError
from app.models import RAGChunk, RAGQuery, db
from flask import current_app
from sentence_transformers import SentenceTransformer
import tiktoken
from annoy import AnnoyIndex
import tempfile

# Suppress PyTorch deprecation warnings
warnings.filterwarnings("ignore", message=".*encoder_attention_mask.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*ARC4.*", category=DeprecationWarning)

logger = logging.getLogger(__name__)

# Global flag to completely disable RAG functionality
RAG_ENABLED = os.environ.get('ENABLE_RAG', 'false').lower() == 'true'

def log_rag_event(event_type: str, details: Dict[str, Any], level: str = "info"):
    """Structured logging for RAG events"""
    log_data = {
        "service": "rag",
        "event_type": event_type,
        "timestamp": time.time(),
        "details": details
    }
    
    if level == "error":
        logger.error(json.dumps(log_data))
    elif level == "warning":
        logger.warning(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))

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
        self._dependencies_available = False
        
        # Environment variable configuration
        self.enabled = RAG_ENABLED
        self.model_name = os.environ.get('RAG_MODEL', 'all-MiniLM-L6-v2')
        self.max_tokens = int(os.environ.get('RAG_MAX_TOKENS', '500'))
        self.chunk_overlap = int(os.environ.get('RAG_CHUNK_OVERLAP', '50'))
        
        # Initialize ANNOY_INDEX_PATH from configuration
        try:
            if current_app:
                # Get from Flask app configuration
                self.ANNOY_INDEX_PATH = current_app.config.get('ANNOY_INDEX_PATH')
                if not self.ANNOY_INDEX_PATH:
                    # Fallback to environment variable
                    self.ANNOY_INDEX_PATH = os.environ.get('ANNOY_INDEX_PATH')
                    if not self.ANNOY_INDEX_PATH:
                        # Default path
                        self.ANNOY_INDEX_PATH = '/var/data/annoy_indices/index.ann'
            else:
                # No Flask app context, use environment variable or default
                self.ANNOY_INDEX_PATH = os.environ.get('ANNOY_INDEX_PATH', '/var/data/annoy_indices/index.ann')
            
            # Ensure the directory exists
            index_dir = os.path.dirname(self.ANNOY_INDEX_PATH)
            if not os.path.exists(index_dir):
                try:
                    os.makedirs(index_dir, exist_ok=True)
                    logger.info(f"Created Annoy index directory: {index_dir}")
                except Exception as e:
                    logger.error(f"Failed to create Annoy index directory {index_dir}: {e}")
                    # Fallback to a writable location
                    self.ANNOY_INDEX_PATH = os.path.join(tempfile.gettempdir(), 'annoy_indices', 'index.ann')
                    fallback_dir = os.path.dirname(self.ANNOY_INDEX_PATH)
                    os.makedirs(fallback_dir, exist_ok=True)
                    logger.info(f"Using fallback Annoy index path: {self.ANNOY_INDEX_PATH}")
            
            logger.info(f"Annoy index path configured: {self.ANNOY_INDEX_PATH}")
            
        except Exception as e:
            logger.error(f"Failed to configure ANNOY_INDEX_PATH: {e}")
            # Critical error - disable RAG service
            self.enabled = False
            self.ANNOY_INDEX_PATH = None
        
        logger.info(f"RAG Service initialized - Enabled: {self.enabled}, Model: {self.model_name}")
        
        # DO NOT initialize anything here - wait until first use
    
    def _check_dependencies(self):
        """Enhanced dependency checking with detailed diagnostics"""
        missing_deps = []
        import_errors = {}
        
        try:
            logger.info(f"tiktoken available: version {getattr(tiktoken, '__version__', 'unknown')}")
        except ImportError as e:
            missing_deps.append('tiktoken')
            import_errors['tiktoken'] = str(e)
            logger.error(f"tiktoken import failed: {e}")
        
        try:
            logger.info("annoy available")
        except ImportError as e:
            missing_deps.append('annoy')
            import_errors['annoy'] = str(e)
            logger.error(f"annoy import failed: {e}")
        
        try:
            logger.info("sentence_transformers available")
        except ImportError as e:
            missing_deps.append('sentence_transformers')
            import_errors['sentence_transformers'] = str(e)
            logger.error(f"sentence_transformers import failed: {e}")
        
        # Check if we have enough dependencies to run
        if len(missing_deps) == 0:
            logger.info("All RAG dependencies available")
            return True
        else:
            logger.warning(f"Missing RAG dependencies: {missing_deps}")
            return False

    def _lazy_init(self) -> bool:
        """Lazy initialization of RAG components"""
        if self._initialized:
            return True
            
        if not self.enabled:
            log_rag_event("lazy_init_disabled", {"message": "RAG service is disabled"})
            return False
        
        # Check if ANNOY_INDEX_PATH is properly configured
        if not hasattr(self, 'ANNOY_INDEX_PATH') or not self.ANNOY_INDEX_PATH:
            log_rag_event("lazy_init_no_index_path", {"message": "ANNOY_INDEX_PATH not configured"}, "error")
            return False
            
        try:
            # Check if required environment variables are set
            if not os.environ.get('OPENAI_API_KEY'):
                log_rag_event("lazy_init_no_openai", {"message": "OpenAI API key not configured"})
                return False
                
            # Initialize sentence transformer model
            model_name = os.environ.get('RAG_MODEL', 'all-MiniLM-L6-v2')
            log_rag_event("lazy_init_model", {"model_name": model_name})
            
            self._model = SentenceTransformer(model_name)
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
            
            # Initialize Annoy index
            self._annoy_index = AnnoyIndex(self._model.get_sentence_embedding_dimension(), 'angular')
            self._embeddings_list = []
            
            # Load existing index if available
            if os.path.exists(self.ANNOY_INDEX_PATH):
                try:
                    self._annoy_index.load(self.ANNOY_INDEX_PATH)
                    self._embeddings_list = self._load_existing_embeddings()
                    log_rag_event("lazy_init_index_loaded", {"index_path": self.ANNOY_INDEX_PATH})
                except Exception as e:
                    log_rag_event("lazy_init_index_load_error", {"error": str(e)}, "warning")
                    # Continue without existing index
            else:
                log_rag_event("lazy_init_no_existing_index", {"index_path": self.ANNOY_INDEX_PATH})
            
            self._initialized = True
            log_rag_event("lazy_init_success", {"message": "RAG service initialized successfully"})
            return True
            
        except Exception as e:
            log_rag_event("lazy_init_error", {"error": str(e)}, "error")
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
            'dependencies_available': self._dependencies_available,
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
                    # Handle JSON format embeddings (list of floats)
                    if isinstance(chunk.embedding, list):
                        embedding = np.array(chunk.embedding, dtype=np.float32)
                    else:
                        # Fallback for old binary format
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
            log_rag_event("store_disabled", {"document_id": document_id, "chunk_count": len(chunks)}, "warning")
            return False
            
        try:
            # Delete existing chunks for this document (use Integer directly)
            deleted_count = RAGChunk.query.filter_by(document_id=document_id).delete()
            db.session.commit()
            log_rag_event("store_delete_existing", {"document_id": document_id, "deleted_count": deleted_count})
            
            chunk_objects = []
            embeddings_to_add = []
            
            # Try lazy initialization for embeddings
            can_generate_embeddings = self._lazy_init()
            
            for i, chunk_text in enumerate(chunks):
                embedding = None
                embedding_json = None
                
                if can_generate_embeddings:
                    embedding = self.generate_embedding(chunk_text)
                    if embedding is not None:
                        # Convert numpy array to JSON-serializable list
                        embedding_json = embedding.tolist()
                        embeddings_to_add.append(embedding)
                
                chunk = RAGChunk(
                    document_id=document_id,  # Use integer directly
                    chunk_index=i,
                    chunk_text=chunk_text,
                    embedding=embedding_json  # Store as JSON list
                )
                chunk_objects.append(chunk)
            
            # Use bulk_save_objects for better performance
            db.session.bulk_save_objects(chunk_objects)
            db.session.commit()
            
            # Add embeddings to Annoy index if available
            if embeddings_to_add and can_generate_embeddings:
                start_index = len(self._embeddings_list)
                for i, embedding in enumerate(embeddings_to_add):
                    self._annoy_index.add_item(start_index + i, embedding)
                    self._embeddings_list.append(embedding)
                
                self._annoy_index.build(10)
                
                # Save index with proper error handling
                try:
                    if hasattr(self, 'ANNOY_INDEX_PATH') and self.ANNOY_INDEX_PATH:
                        self._annoy_index.save(self.ANNOY_INDEX_PATH)
                        log_rag_event("index_saved", {"index_path": self.ANNOY_INDEX_PATH})
                    else:
                        log_rag_event("index_save_skipped", {"reason": "ANNOY_INDEX_PATH not configured"}, "warning")
                except Exception as e:
                    log_rag_event("index_save_error", {"error": str(e)}, "error")
            
            log_rag_event("store_success", {
                "document_id": document_id, 
                "chunk_count": len(chunks),
                "embeddings_generated": len(embeddings_to_add)
            })
            return True
            
        except SQLAlchemyError as e:
            log_rag_event("store_database_error", {"error": str(e), "document_id": document_id}, "error")
            db.session.rollback()
            return False
        except Exception as e:
            log_rag_event("store_error", {"error": str(e), "document_id": document_id}, "error")
            db.session.rollback()
            return False
    
    def search_similar_chunks(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity"""
        if not self.enabled:
            log_rag_event("search_disabled", {"query": query, "top_k": top_k}, "warning")
            return self._fallback_text_search(query, top_k)
            
        # Try lazy initialization
        if not self._lazy_init():
            log_rag_event("search_unavailable", {"query": query, "top_k": top_k}, "warning")
            return self._fallback_text_search(query, top_k)
            
        try:
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                log_rag_event("embedding_failed", {"query": query}, "warning")
                return self._fallback_text_search(query, top_k)
            
            # Search Annoy index
            query_vector = query_embedding.tolist()
            indices = self._annoy_index.get_nns_by_vector(query_vector, top_k, include_distances=True)
            
            # Get corresponding chunks from database
            results = []
            chunks = RAGChunk.query.filter(RAGChunk.embedding.isnot(None)).all()
            
            if not chunks:
                log_rag_event("no_chunks_found", {"query": query}, "warning")
                return self._fallback_text_search(query, top_k)
            
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
            log_rag_event("search_success", {
                "query": query, 
                "results_count": len(results),
                "total_chunks": len(chunks)
            })
            return results
            
        except Exception as e:
            log_rag_event("search_error", {"query": query, "error": str(e)}, "error")
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
        return self._lazy_init()
    
    def generate_rag_answer(self, question: str, document_text: str) -> Optional[str]:
        """Generate an answer to a question using RAG on the provided document text"""
        if not self.is_available():
            logger.warning("RAG service not available for answer generation")
            return None
        
        try:
            # Chunk the document text
            chunks = self.chunk_text(document_text)
            if not chunks:
                logger.warning("No chunks generated from document text")
                return None
            
            # Store chunks temporarily for this query
            temp_document_id = 999999  # Temporary ID
            self.store_document_chunks(temp_document_id, chunks)
            
            # Search for relevant chunks
            relevant_chunks = self.search_similar_chunks(question, top_k=3)
            if not relevant_chunks:
                logger.warning("No relevant chunks found for question")
                return None
            
            # Combine relevant chunks for context
            context = "\n\n".join([chunk['chunk_text'] for chunk in relevant_chunks])
            
            # Get OpenAI API key from environment (not Flask config)
            openai_api_key = os.environ.get('OPENAI_API_KEY')
            if not openai_api_key:
                logger.error("OpenAI API key not found in environment variables")
                # Debug: show what environment variables we do have
                env_keys = [k for k in os.environ.keys() if 'API' in k or 'OPENAI' in k]
                logger.error(f"Available API-related env vars: {env_keys}")
                return None
            
            logger.info(f"✅ OpenAI key loaded: {openai_api_key[:10]}...")
            
            # Use OpenAI client with environment variable
            import openai
            client = openai.OpenAI(api_key=openai_api_key)
            
            prompt = f"""Based on the following document context, answer the question.

Document Context:
{context}

Question: {question}

Please provide a clear and accurate answer based only on the information in the document context."""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on document content. Only use information from the provided document context."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
            
            answer = response.choices[0].message.content.strip()
            
            # Clean up temporary chunks
            try:
                RAGChunk.query.filter_by(document_id=temp_document_id).delete()
                db.session.commit()
            except Exception as e:
                logger.warning(f"Failed to clean up temporary chunks: {e}")
            
            return answer
            
        except Exception as e:
            logger.error(f"Error generating RAG answer: {e}")
            return None

def get_rag_service():
    """Factory function to get RAG service instance - only creates when needed"""
    return RAGService() 