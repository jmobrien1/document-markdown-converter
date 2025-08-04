#!/usr/bin/env python3
"""
Script to install ML dependencies when RAG is enabled
Enhanced version with better error handling and logging
"""
import os
import subprocess
import sys
import traceback

def install_ml_dependencies():
    """Install ML dependencies if RAG is enabled"""
    print("=" * 60)
    print("🔧 ML Dependencies Installation Script")
    print("=" * 60)
    
    # Check environment
    rag_enabled = os.environ.get('ENABLE_RAG', 'false').lower() == 'true'
    print(f"🔍 Environment Check:")
    print(f"   ENABLE_RAG: {os.environ.get('ENABLE_RAG', 'not set')}")
    print(f"   RAG enabled: {rag_enabled}")
    print(f"   Current directory: {os.getcwd()}")
    print(f"   Python executable: {sys.executable}")
    print(f"   Python version: {sys.version}")
    
    if not rag_enabled:
        print("❌ RAG is disabled (ENABLE_RAG=false). Skipping ML dependency installation.")
        return False
    
    print("✅ RAG is enabled (ENABLE_RAG=true). Installing ML dependencies...")
    
    # Check if requirements-ml.txt exists
    if not os.path.exists('requirements-ml.txt'):
        print("❌ requirements-ml.txt not found. Creating it...")
        create_ml_requirements()
    
    # Verify requirements-ml.txt exists and has content
    if not os.path.exists('requirements-ml.txt'):
        print("❌ Failed to create requirements-ml.txt")
        return False
    
    with open('requirements-ml.txt', 'r') as f:
        content = f.read()
        print(f"📋 requirements-ml.txt content ({len(content)} chars):")
        print(content)
    
    try:
        print("📦 Installing ML dependencies from requirements-ml.txt...")
        
        # Use subprocess with explicit python path
        cmd = [sys.executable, '-m', 'pip', 'install', '-r', 'requirements-ml.txt', '--verbose']
        print(f"🚀 Running command: {' '.join(cmd)}")
        
        # Run with timeout and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(f"📊 Command completed with return code: {result.returncode}")
        
        if result.stdout:
            print("📤 STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("📤 STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ ML dependencies installed successfully!")
            
            # Verify key packages are installed
            verify_installations()
            return True
        else:
            print(f"❌ Failed to install ML dependencies (exit code: {result.returncode})")
            print("🔄 RAG service will be disabled due to missing dependencies.")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Installation timed out after 5 minutes")
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
        traceback.print_exc()
        return False

def verify_installations():
    """Verify that key ML packages are installed"""
    print("🔍 Verifying installations...")
    
    key_packages = [
        'tiktoken',
        'sentence_transformers', 
        'numpy',
        'torch',
        'transformers',
        'annoy'
    ]
    
    for package in key_packages:
        try:
            __import__(package)
            print(f"✅ {package} - OK")
        except ImportError:
            print(f"❌ {package} - FAILED")

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
    
    try:
        with open('requirements-ml.txt', 'w') as f:
            f.write(ml_requirements)
        print("✅ Created requirements-ml.txt")
    except Exception as e:
        print(f"❌ Failed to create requirements-ml.txt: {e}")

if __name__ == '__main__':
    print("🚀 Starting ML Dependencies Installation")
    print(f"⏰ Timestamp: {os.popen('date').read().strip()}")
    
    success = install_ml_dependencies()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ML dependencies ready for RAG service!")
        print("✅ Installation completed successfully")
    else:
        # Set environment variable to disable RAG
        os.environ['ENABLE_RAG'] = 'false'
        print("🔄 RAG service disabled due to installation failures.")
        print("⚠️  Application will run without RAG features")
    
    print("=" * 60) 