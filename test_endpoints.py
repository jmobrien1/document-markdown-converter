#!/usr/bin/env python3
"""
Test script for API endpoints
"""
import requests
import json
import sys

# Configuration
BASE_URL = "https://mdraft-app.onrender.com"  # Replace with your actual URL
API_KEY = "afcc8ca6e3b697a827d9439fa280a478c164d8b6c454c605504356453fa25965"  # Your API key

def test_health_endpoint():
    """Test the health endpoint"""
    print("🔍 Testing Health Endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/health")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health endpoint working!")
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Health endpoint failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing health endpoint: {e}")
        return False

def test_summarize_endpoint():
    """Test the summarize endpoint"""
    print("\n🔍 Testing Summarize Endpoint...")
    
    # You need a valid conversion ID for this test
    conversion_id = "test-conversion-id"  # Replace with actual conversion ID
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "length": "medium"  # short, medium, long
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/conversion/{conversion_id}/summarize",
            headers=headers,
            json=data
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("✅ Summarize endpoint working!")
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        elif response.status_code == 401:
            print("❌ Authentication failed - check your API key")
            return False
        elif response.status_code == 404:
            print("❌ Conversion not found - use a valid conversion ID")
            return False
        else:
            print(f"❌ Summarize endpoint failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing summarize endpoint: {e}")
        return False

def test_query_endpoint():
    """Test the RAG query endpoint"""
    print("\n🔍 Testing RAG Query Endpoint...")
    
    # You need a valid conversion ID for this test
    conversion_id = "test-conversion-id"  # Replace with actual conversion ID
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "question": "What is the main topic of this document?"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/conversion/{conversion_id}/query",
            headers=headers,
            json=data
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("✅ Query endpoint working!")
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        elif response.status_code == 401:
            print("❌ Authentication failed - check your API key")
            return False
        elif response.status_code == 404:
            print("❌ Conversion not found - use a valid conversion ID")
            return False
        else:
            print(f"❌ Query endpoint failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing query endpoint: {e}")
        return False

def test_robots_txt():
    """Test robots.txt endpoint"""
    print("\n🔍 Testing robots.txt...")
    try:
        response = requests.get(f"{BASE_URL}/robots.txt")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ robots.txt working!")
            print(f"Content: {response.text}")
            return True
        else:
            print(f"❌ robots.txt failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing robots.txt: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting API Endpoint Tests")
    print("=" * 50)
    
    # Check if API key is configured
    if API_KEY == "your-api-key-here":
        print("❌ Please update the API_KEY variable in this script")
        print("   Get your API key by running: python3 get_api_key.py")
        return
    
    # Run tests
    tests = [
        test_health_endpoint,
        test_summarize_endpoint,
        test_query_endpoint,
        test_robots_txt
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print(f"✅ Passed: {sum(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.")

if __name__ == "__main__":
    main() 