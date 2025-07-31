// Debug script to test form submission
async function debugFormSubmission() {
    console.log("=== DEBUGGING FORM SUBMISSION ===");
    
    // Check if form exists
    const uploadForm = document.getElementById('uploadForm');
    console.log("1. Form found:", uploadForm);
    
    if (!uploadForm) {
        console.error("❌ Form not found!");
        return;
    }
    
    // Check form attributes
    console.log("2. Form attributes:", {
        method: uploadForm.method,
        action: uploadForm.action,
        enctype: uploadForm.enctype
    });
    
    // Check file input
    const fileInput = document.getElementById('fileInput');
    console.log("3. File input found:", fileInput);
    
    if (fileInput && fileInput.files.length > 0) {
        console.log("4. File selected:", fileInput.files[0].name, fileInput.files[0].size, "bytes");
        
        // Test FormData creation
        const formData = new FormData(uploadForm);
        console.log("5. FormData created from form");
        
        // Check what's in the FormData
        console.log("6. FormData contents:");
        for (let [key, value] of formData.entries()) {
            console.log(`   ${key}:`, value);
        }
        
        // Test the actual submission
        console.log("7. Testing submission...");
        try {
            const response = await fetch(uploadForm.action, {
                method: uploadForm.method,
                body: formData
            });
            
            console.log("8. Response status:", response.status);
            const responseText = await response.text();
            console.log("9. Response body:", responseText);
            
            if (response.ok) {
                console.log("✅ SUCCESS: Form submission worked!");
            } else {
                console.log("❌ ERROR: Form submission failed");
            }
        } catch (error) {
            console.error("❌ FETCH ERROR:", error);
        }
    } else {
        console.log("4. No file selected - please select a file first");
    }
    
    console.log("=== DEBUG COMPLETE ===");
}

// Run the debug
debugFormSubmission(); 