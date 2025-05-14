document.addEventListener('DOMContentLoaded', function() {
    const uploadBtn = document.getElementById('upload-btn');
    const fileInput = document.getElementById('resume-upload');
    const fileNameDisplay = document.getElementById('file-name');
    const uploadContainer = document.getElementById('upload-container');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const errorMessage = document.getElementById('error-message');

    // Trigger file input when button is clicked
    uploadBtn.addEventListener('click', function() {
        fileInput.click();
    });

    // Handle file selection
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            fileNameDisplay.textContent = `Selected: ${file.name}`;
            fileNameDisplay.classList.remove('hidden');
            
            // Upload the file
            uploadFile(file);
        }
    });

    // Drag and drop functionality
    uploadContainer.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadContainer.classList.add('border-indigo-500', 'bg-indigo-50');
    });

    uploadContainer.addEventListener('dragleave', function() {
        uploadContainer.classList.remove('border-indigo-500', 'bg-indigo-50');
    });

    uploadContainer.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadContainer.classList.remove('border-indigo-500', 'bg-indigo-50');
        
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            const file = e.dataTransfer.files[0];
            fileNameDisplay.textContent = `Selected: ${file.name}`;
            fileNameDisplay.classList.remove('hidden');
            
            // Upload the file
            uploadFile(file);
        }
    });

    function uploadFile(file) {
        // Validate file type
        const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
        if (!validTypes.includes(file.type) && !file.name.match(/\.(pdf|docx|txt)$/i)) {
            showError('Please upload a PDF, DOCX, or TXT file.');
            return;
        }

        // Validate file size (max 5MB)
        if (file.size > 5 * 1024 * 1024) {
            showError('File size should be less than 5MB.');
            return;
        }

        // Prepare form data
        const formData = new FormData();
        formData.append('file', file);

        // Show progress
        progressContainer.classList.remove('hidden');
        uploadBtn.disabled = true;

        // Simulate progress (in a real app, you'd use actual upload progress)
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress > 90) {
                clearInterval(progressInterval);
            }
            updateProgress(progress);
        }, 200);

        // Make AJAX request
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            clearInterval(progressInterval);
            updateProgress(100);
            
            if (!response.ok) {
                return response.json().then(err => { throw err; });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                // Redirect to results page with the parsed data
                window.location.href = `/results?data=${encodeURIComponent(JSON.stringify(data.parsed_resume))}`;
            } else {
                showError(data.error || 'Failed to parse resume');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showError(error.error || 'An error occurred while processing your file');
        })
        .finally(() => {
            uploadBtn.disabled = false;
        });
    }

    function updateProgress(percent) {
        progressBar.style.width = `${percent}%`;
        progressPercent.textContent = `${percent}%`;
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove('hidden');
        setTimeout(() => {
            errorMessage.classList.add('hidden');
        }, 5000);
    }

    // Check if we have results data in URL (for direct linking)
    const urlParams = new URLSearchParams(window.location.search);
    const resultsData = urlParams.get('data');
    if (resultsData) {
        try {
            const parsedData = JSON.parse(decodeURIComponent(resultsData));
            displayResults(parsedData);
        } catch (e) {
            console.error('Error parsing results data:', e);
        }
    }
});

function displayResults(data) {
    // This would be handled by the results.html template in our case
    // For a single-page app approach, you would render the results here
}