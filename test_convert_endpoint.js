// Test script to debug the convert endpoint
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
        console.error("POST Error (no file):", error);
    }
    
    // Test 3 & 4: Check form and file input (manual check needed)
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

// Run the test
testConvertEndpoint(); 