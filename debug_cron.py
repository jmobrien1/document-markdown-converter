#!/usr/bin/env python3
"""
Debug script for cron job path issues
"""

import os
import sys

def main():
    print("=== Cron Job Debug Information ===")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Script location: {__file__}")
    
    print("\n=== Directory Contents ===")
    try:
        for item in os.listdir('.'):
            print(f"  {item}")
    except Exception as e:
        print(f"Error listing directory: {e}")
    
    print("\n=== Scripts Directory ===")
    try:
        if os.path.exists('scripts'):
            for item in os.listdir('scripts'):
                print(f"  scripts/{item}")
        else:
            print("  scripts/ directory does not exist")
    except Exception as e:
        print(f"Error listing scripts directory: {e}")
    
    print("\n=== Environment Variables ===")
    for key, value in os.environ.items():
        if 'RENDER' in key or 'PATH' in key or 'PYTHON' in key:
            print(f"  {key}: {value}")
    
    print("\n=== Testing Script Execution ===")
    script_path = 'scripts/run_cron_tasks.py'
    if os.path.exists(script_path):
        print(f"✅ {script_path} exists")
        try:
            with open(script_path, 'r') as f:
                first_line = f.readline().strip()
                print(f"First line: {first_line}")
        except Exception as e:
            print(f"Error reading script: {e}")
    else:
        print(f"❌ {script_path} does not exist")
        
        # Try alternative paths
        alt_paths = [
            '/opt/render/project/src/scripts/run_cron_tasks.py',
            './scripts/run_cron_tasks.py',
            'scripts/run_cron_tasks.py',
            '../scripts/run_cron_tasks.py'
        ]
        
        for path in alt_paths:
            if os.path.exists(path):
                print(f"✅ Found at: {path}")
                break
        else:
            print("❌ Script not found in any expected location")

if __name__ == "__main__":
    main() 