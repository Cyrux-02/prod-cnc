// Client-side image validation and upload handler
async function validateAndUploadImage(file) {
    // Validate file type
    if (!file.type.startsWith('image/')) {
        throw new Error('Please select an image file (PNG, JPG, GIF)');
    }
    
    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
        throw new Error('File size should be less than 5MB');
    }
    
    // Validate image dimensions
    await validateImageDimensions(file);
    
    // Create form data and upload
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch('/upload_profile_pic', {
        method: 'POST',
        body: formData
    });
    
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || 'Failed to upload profile picture');
    }
    return data;
}

function validateImageDimensions(file) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        const objectUrl = URL.createObjectURL(file);
        
        img.onload = function() {
            URL.revokeObjectURL(objectUrl);
            
            if (img.width > 2000 || img.height > 2000) {
                reject(new Error('Image dimensions should be less than 2000x2000 pixels'));
                return;
            }
            
            if (img.width < 100 || img.height < 100) {
                reject(new Error('Image dimensions should be at least 100x100 pixels'));
                return;
            }
            
            resolve();
        };
        
        img.onerror = function() {
            URL.revokeObjectURL(objectUrl);
            reject(new Error('Invalid image file'));
        };
        
        img.src = objectUrl;
    });
}
