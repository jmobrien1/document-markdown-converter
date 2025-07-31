// Debug script for testing file conversion
// Run this in your browser console on https://mdraft.onrender.com

async function debugConversion() {
    console.log("=== DEBUGGING CONVERSION ===");
    
    // 1. Check user status
    console.log("1. Checking user status...");
    const userResponse = await fetch('/user-status');
    const userData = await userResponse.json();
    console.log("User Status:", userData);
    
    // 2. Check form elements
    console.log("2. Checking form elements...");
    const proCheckbox = document.getElementById('pro_conversion');
    const proTab = document.getElementById('pro-tab');
    const standardTab = document.getElementById('standard-tab');
    const fileInput = document.getElementById('file-input') || document.querySelector('input[type="file"]');
    const proConversionHidden = document.getElementById('pro_conversion_hidden_input');
    
    console.log("Form Elements:", {
        proCheckbox: proCheckbox,
        proCheckboxDisabled: proCheckbox?.disabled,
        proTab: proTab,
        standardTab: standardTab,
        fileInput: fileInput,
        hasFile: fileInput?.files?.length > 0,
        proConversionHidden: proConversionHidden,
        hiddenValue: proConversionHidden?.value
    });
    
    // 3. Check current tab state
    console.log("3. Checking tab state...");
    if (proTab && standardTab) {
        console.log("Tab States:", {
            proTabActive: proTab.classList.contains('active'),
            standardTabActive: standardTab.classList.contains('active'),
            proTabDisabled: proTab.disabled,
            standardTabDisabled: standardTab.disabled
        });
    }
    
    // 4. Try a test conversion if file is selected
    if (fileInput && fileInput.files.length > 0) {
        console.log("4. Testing conversion...");
        const file = fileInput.files[0];
        console.log("Selected file:", {
            name: file.name,
            size: file.size,
            type: file.type
        });
        
        const formData = new FormData();
        formData.append('file', file);
        
        // Check if Pro conversion is selected
        const isProSelected = proTab && proTab.classList.contains('active');
        if (isProSelected) {
            formData.append('pro_conversion', 'on');
            console.log("Pro conversion selected");
        } else {
            console.log("Standard conversion selected");
        }
        
        console.log("Sending conversion request...");
        
        try {
            const response = await fetch('/convert', {
                method: 'POST',
                body: formData
            });
            
            const responseText = await response.text();
            console.log("Response Status:", response.status);
            console.log("Response Headers:", Object.fromEntries(response.headers.entries()));
            console.log("Response Text:", responseText);
            
            if (!response.ok) {
                console.error("CONVERSION FAILED:", responseText);
            } else {
                console.log("Conversion request successful!");
            }
        } catch (error) {
            console.error("FETCH ERROR:", error);
        }
    } else {
        console.log("4. No file selected - please select a file first");
    }
}

// Also provide a simple test function
function testWithSampleFile() {
    console.log("=== TESTING WITH SAMPLE FILE ===");
    
    // Create a simple text file for testing
    const testContent = "This is a test document for conversion.";
    const testFile = new File([testContent], "test.txt", { type: "text/plain" });
    
    // Simulate file input
    const fileInput = document.getElementById('file-input') || document.querySelector('input[type="file"]');
    if (fileInput) {
        // Create a DataTransfer object to set files
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(testFile);
        fileInput.files = dataTransfer.files;
        
        console.log("Test file set:", testFile.name);
        debugConversion();
    } else {
        console.error("File input not found");
    }
}

// Export functions for console use
window.debugConversion = debugConversion;
window.testWithSampleFile = testWithSampleFile;

console.log("Debug functions loaded:");
console.log("- debugConversion() - Test with selected file");
console.log("- testWithSampleFile() - Test with sample text file"); 