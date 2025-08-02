# app/services/rag_service.py
# RAG (Retrieval-Augmented Generation) service for citation-backed Q&A

import os
import json
import pickle
import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import tiktoken
from sentence_transformers import SentenceTransformer
import faiss
from flask import current_app

from app import db
from app.models import Conversion, RAGChunk, RAGQuery


class RAGService:
    """Service for handling RAG pipeline operations."""
    
    def __init__(self):
        # Initialize sentence transformer model
        self.model_name = "all-MiniLM-L6-v2"  # Fast, good quality
        self.model = SentenceTransformer(self.model_name)
        
        # Chunking parameters
        self.chunk_size = 256  # tokens
        self.chunk_overlap = 64  # tokens
        
        # Search parameters
        self.top_k = 5  # Number of chunks to retrieve
        
        # Initialize tokenizer
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Vector storage directory
        self.vector_dir = "vector_storage"
        os.makedirs(self.vector_dir, exist_ok=True)
    
    def chunk_text(self, text: str) -> List[Dict[str, any]]:
        """
        Split text into overlapping semantic chunks.
        
        Args:
            text: The text to chunk
            
        Returns:
            List of chunk dictionaries with 'text', 'start_token', 'end_token', 'chunk_id'
        """
        try:
            # Tokenize the text
            tokens = self.tokenizer.encode(text)
            
            chunks = []
            chunk_id = 0
            
            for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
                # Get chunk tokens
                chunk_tokens = tokens[i:i + self.chunk_size]
                
                # Decode back to text
                chunk_text = self.tokenizer.decode(chunk_tokens)
                
                # Skip empty chunks
                if not chunk_text.strip():
                    continue
                
                chunk_data = {
                    'text': chunk_text.strip(),
                    'start_token': i,
                    'end_token': min(i + self.chunk_size, len(tokens)),
                    'chunk_id': chunk_id,
                    'token_count': len(chunk_tokens)
                }
                
                chunks.append(chunk_data)
                chunk_id += 1
            
            current_app.logger.info(f"Created {len(chunks)} chunks from text")
            return chunks
            
        except Exception as e:
            current_app.logger.error(f"Error chunking text: {e}")
            raise Exception(f"Failed to chunk text: {str(e)}")
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            numpy array of embeddings
        """
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            current_app.logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings
            
        except Exception as e:
            current_app.logger.error(f"Error generating embeddings: {e}")
            raise Exception(f"Failed to generate embeddings: {str(e)}")
    
    def create_vector_index(self, conversion_id: int, chunks: List[Dict], embeddings: np.ndarray) -> str:
        """
        Create and save a FAISS index for the document chunks.
        
        Args:
            conversion_id: ID of the conversion
            chunks: List of chunk dictionaries
            embeddings: numpy array of embeddings
            
        Returns:
            Path to the saved index file
        """
        try:
            # Create FAISS index
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
            
            # Normalize embeddings for cosine similarity
            faiss.normalize_L2(embeddings)
            
            # Add vectors to index
            index.add(embeddings.astype('float32'))
            
            # Save index and metadata
            index_path = os.path.join(self.vector_dir, f"index_{conversion_id}.faiss")
            metadata_path = os.path.join(self.vector_dir, f"metadata_{conversion_id}.json")
            
            # Save FAISS index
            faiss.write_index(index, index_path)
            
            # Save metadata
            metadata = {
                'conversion_id': conversion_id,
                'chunks': chunks,
                'embedding_dimension': dimension,
                'created_at': datetime.utcnow().isoformat()
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            current_app.logger.info(f"Created vector index for conversion {conversion_id}")
            return index_path
            
        except Exception as e:
            current_app.logger.error(f"Error creating vector index: {e}")
            raise Exception(f"Failed to create vector index: {str(e)}")
    
    def process_document(self, conversion_id: int, text: str) -> bool:
        """
        Process a document through the RAG pipeline.
        
        Args:
            conversion_id: ID of the conversion
            text: Document text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            current_app.logger.info(f"Processing document for conversion {conversion_id}")
            
            # Step 1: Chunk the text
            chunks = self.chunk_text(text)
            
            if not chunks:
                current_app.logger.warning(f"No chunks created for conversion {conversion_id}")
                return False
            
            # Step 2: Generate embeddings
            chunk_texts = [chunk['text'] for chunk in chunks]
            embeddings = self.generate_embeddings(chunk_texts)
            
            # Step 3: Create vector index
            index_path = self.create_vector_index(conversion_id, chunks, embeddings)
            
            # Step 4: Save chunks to database
            self._save_chunks_to_db(conversion_id, chunks)
            
            current_app.logger.info(f"Successfully processed document for conversion {conversion_id}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Error processing document: {e}")
            return False
    
    def _save_chunks_to_db(self, conversion_id: int, chunks: List[Dict]) -> None:
        """Save chunks to database."""
        try:
            for chunk in chunks:
                rag_chunk = RAGChunk(
                    conversion_id=conversion_id,
                    chunk_id=chunk['chunk_id'],
                    text=chunk['text'],
                    start_token=chunk['start_token'],
                    end_token=chunk['end_token'],
                    token_count=chunk['token_count']
                )
                db.session.add(rag_chunk)
            
            db.session.commit()
            current_app.logger.info(f"Saved {len(chunks)} chunks to database")
            
        except Exception as e:
            current_app.logger.error(f"Error saving chunks to database: {e}")
            db.session.rollback()
    
    def query_document(self, conversion_id: int, question: str) -> Dict:
        """
        Query a document with a question using RAG.
        
        Args:
            conversion_id: ID of the conversion
            question: User's question
            
        Returns:
            Dictionary with answer, citations, and metadata
        """
        try:
            current_app.logger.info(f"Querying document {conversion_id}: {question}")
            
            # Step 1: Load vector index and metadata
            index_path = os.path.join(self.vector_dir, f"index_{conversion_id}.faiss")
            metadata_path = os.path.join(self.vector_dir, f"metadata_{conversion_id}.json")
            
            if not os.path.exists(index_path) or not os.path.exists(metadata_path):
                raise Exception(f"Vector index not found for conversion {conversion_id}")
            
            # Load index
            index = faiss.read_index(index_path)
            
            # Load metadata
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Step 2: Embed the question
            question_embedding = self.model.encode([question], convert_to_numpy=True)
            faiss.normalize_L2(question_embedding)
            
            # Step 3: Search for similar chunks
            scores, indices = index.search(question_embedding.astype('float32'), self.top_k)
            
            # Step 4: Retrieve relevant chunks
            relevant_chunks = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(metadata['chunks']):
                    chunk = metadata['chunks'][idx]
                    relevant_chunks.append({
                        'chunk_id': chunk['chunk_id'],
                        'text': chunk['text'],
                        'score': float(score),
                        'rank': i + 1
                    })
            
            # Step 5: Generate answer using LLM
            answer, citations = self._generate_answer_with_citations(question, relevant_chunks)
            
            # Step 6: Save query to database
            self._save_query_to_db(conversion_id, question, answer, citations)
            
            return {
                'answer': answer,
                'citations': citations,
                'relevant_chunks': relevant_chunks,
                'conversion_id': conversion_id
            }
            
        except Exception as e:
            current_app.logger.error(f"Error querying document: {e}")
            raise Exception(f"Failed to query document: {str(e)}")
    
    def _generate_answer_with_citations(self, question: str, relevant_chunks: List[Dict]) -> Tuple[str, List[Dict]]:
        """
        Generate answer using LLM with citations.
        
        Args:
            question: User's question
            relevant_chunks: List of relevant chunks
            
        Returns:
            Tuple of (answer, citations)
        """
        try:
            # Construct context from relevant chunks
            context = "\n\n".join([f"[Chunk {chunk['chunk_id']}]: {chunk['text']}" for chunk in relevant_chunks])
            
            # Create prompt for LLM
            prompt = f"""Based on the following document context, answer the user's question. 
            If the answer cannot be found in the context, say "I cannot answer this question based on the provided document."
            
            Document Context:
            {context}
            
            Question: {question}
            
            Answer with citations in the format [Chunk X] where X is the chunk number:"""
            
            # Call OpenAI API
            import requests
            import os
            
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise Exception("OpenAI API key not configured")
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'gpt-4',
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful assistant that answers questions based on provided document context. Always cite your sources using [Chunk X] format.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 500,
                'temperature': 0.3
            }
            
            response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data)
            
            if response.status_code != 200:
                raise Exception(f"OpenAI API error: {response.text}")
            
            result = response.json()
            answer = result['choices'][0]['message']['content']
            
            # Extract citations from answer
            citations = []
            for chunk in relevant_chunks:
                if f"[Chunk {chunk['chunk_id']}]" in answer:
                    citations.append({
                        'chunk_id': chunk['chunk_id'],
                        'text': chunk['text'],
                        'score': chunk['score']
                    })
            
            return answer, citations
            
        except Exception as e:
            current_app.logger.error(f"Error generating answer: {e}")
            return "I apologize, but I encountered an error while generating the answer.", []
    
    def _save_query_to_db(self, conversion_id: int, question: str, answer: str, citations: List[Dict]) -> None:
        """Save query and answer to database."""
        try:
            rag_query = RAGQuery(
                conversion_id=conversion_id,
                question=question,
                answer=answer,
                citations=json.dumps(citations)
            )
            db.session.add(rag_query)
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error saving query to database: {e}")
            db.session.rollback() 