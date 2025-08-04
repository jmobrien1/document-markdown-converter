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
    
    print(f"🔍 Checking RAG configuration...")
    print(f"ENABLE_RAG environment variable: {os.environ.get('ENABLE_RAG', 'not set')}")
    print(f"RAG enabled: {rag_enabled}")
    
    if not rag_enabled:
        print("❌ RAG is disabled (ENABLE_RAG=false). Skipping ML dependency installation.")
        return False
    
    print("✅ RAG is enabled (ENABLE_RAG=true). Installing ML dependencies...")
    
    # Check if requirements-ml.txt exists
    if not os.path.exists('requirements-ml.txt'):
        print("❌ requirements-ml.txt not found. Creating it...")
        create_ml_requirements()
    
    try:
        print("📦 Installing ML dependencies from requirements-ml.txt...")
        # Install ML dependencies with verbose output
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements-ml.txt'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ ML dependencies installed successfully!")
            print("📋 Installed packages:")
            print(result.stdout)
            return True
        else:
            print(f"❌ Failed to install ML dependencies:")
            print(f"Error: {result.stderr}")
            print("🔄 RAG service will be disabled due to missing dependencies.")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install ML dependencies: {e}")
        print("🔄 RAG service will be disabled due to missing dependencies.")
        return False
    except FileNotFoundError:
        print("❌ requirements-ml.txt not found. RAG service will be disabled.")
        return False
    except Exception as e:
        print(f"❌ Unexpected error installing ML dependencies: {e}")
        print("🔄 RAG service will be disabled due to missing dependencies.")
        return False

def create_ml_requirements():
    """Create requirements-ml.txt if it doesn't exist"""
    ml_requirements = """# ML/RAG Pipeline Dependencies - Only install when ENABLE_RAG=true
tiktoken==0.5.2
sentence-transformers==2.2.2
numpy==1.26.4
scikit-learn==1.3.2
torch==2.1.2
transformers==4.36.2
huggingface-hub==0.20.3

# Vector similarity search alternative (lighter weight)
annoy==1.17.3
"""
    
    with open('requirements-ml.txt', 'w') as f:
        f.write(ml_requirements)
    print("✅ Created requirements-ml.txt")

if __name__ == '__main__':
    success = install_ml_dependencies()
    if not success:
        # Set environment variable to disable RAG
        os.environ['ENABLE_RAG'] = 'false'
        print("🔄 RAG service disabled due to installation failures.")
    else:
        print("🎉 ML dependencies ready for RAG service!") 