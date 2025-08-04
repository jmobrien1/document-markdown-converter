#!/usr/bin/env python3
"""
Script to install ML dependencies when RAG is enabled
"""
import os
import subprocess
import sys

def install_ml_dependencies():
    """Install ML dependencies if RAG is enabled"""
    rag_enabled = os.environ.get('ENABLE_RAG', 'false').lower() == 'true'
    
    if not rag_enabled:
        print("RAG is disabled (ENABLE_RAG=false). Skipping ML dependency installation.")
        return
    
    print("RAG is enabled (ENABLE_RAG=true). Installing ML dependencies...")
    
    try:
        # Install ML dependencies
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements-ml.txt'
        ])
        print("✅ ML dependencies installed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install ML dependencies: {e}")
        print("RAG service will be disabled due to missing dependencies.")
        # Set environment variable to disable RAG
        os.environ['ENABLE_RAG'] = 'false'
        
    except FileNotFoundError:
        print("❌ requirements-ml.txt not found. RAG service will be disabled.")
        os.environ['ENABLE_RAG'] = 'false'

if __name__ == '__main__':
    install_ml_dependencies() 