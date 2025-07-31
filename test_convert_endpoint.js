// Test script for /convert endpoint
// Run this in your browser console on https://mdraft.onrender.com

async function testConvertEndpoint() {
    console.log("=== TESTING /CONVERT ENDPOINT ===");
    
    // Test 1: GET request (should return 405 with helpful message)
    console.log("1. Testing GET request...");
    try {
        const getResponse = await fetch('/convert');
        const getData = await getResponse.json();
        console.log("GET Response:", getResponse.status, getData);
    } catch (error) {
        console.error("GET Error:", error);
    }
    
    // Test 2: POST request without file (should return 400)
    console.log("2. Testing POST request without file...");
    try {
        const formData = new FormData();
        const postResponse = await fetch('/convert', {
            method: 'POST',
            body: formData
        });
        const postData = await postResponse.json();
        console.log("POST Response (no file):", postResponse.status, postData);
    } catch (error) {
        console.error("POST Error:", error);
    }
    
    // Test 3: Check if file input exists
    console.log("3. Checking file input...");
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        console.log("File input found:", fileInput);
        console.log("Has files:", fileInput.files.length > 0);
        if (fileInput.files.length > 0) {
            console.log("Selected file:", fileInput.files[0].name);
        }
    } else {
        console.log("File input not found");
    }
    
    // Test 4: Check form configuration
    console.log("4. Checking form configuration...");
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        console.log("Form found:", {
            method: uploadForm.method,
            action: uploadForm.action,
            enctype: uploadForm.enctype
        });
    } else {
        console.log("Form not found");
    }
    
    console.log("=== TEST COMPLETE ===");
}

// Test with sample file
async function testWithSampleFile() {
    console.log("=== TESTING WITH SAMPLE FILE ===");
    
    // Create a simple text file
    const testContent = "This is a test document for conversion.";
    const testFile = new File([testContent], "test.txt", { type: "text/plain" });
    
    // Create FormData
    const formData = new FormData();
    formData.append('file', testFile);
    formData.append('pro_conversion', 'off');
    
    console.log("Sending test file:", testFile.name, testFile.size, "bytes");
    
    try {
        const response = await fetch('/convert', {
            method: 'POST',
            body: formData
        });
        
        const responseText = await response.text();
        console.log("Response Status:", response.status);
        console.log("Response Headers:", Object.fromEntries(response.headers.entries()));
        console.log("Response Text:", responseText);
        
        if (response.ok) {
            console.log("✅ SUCCESS: File conversion request accepted!");
        } else {
            console.log("❌ ERROR: File conversion request failed");
        }
    } catch (error) {
        console.error("FETCH ERROR:", error);
    }
}

// Export functions
window.testConvertEndpoint = testConvertEndpoint;
window.testWithSampleFile = testWithSampleFile;

console.log("Test functions loaded:");
console.log("- testConvertEndpoint() - Test GET and POST requests");
console.log("- testWithSampleFile() - Test with sample file"); 