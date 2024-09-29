document.addEventListener('DOMContentLoaded', function() {
    // Function to add new crew fields
    function addNewCrewFields() {
        const container = document.getElementById('new-boats');
        const newField = document.createElement('div');
        newField.className = 'd-flex align-items-center mb-1';
        newField.innerHTML = `
            <input type="text" name="boat_[]" class="form-control me-2" placeholder="Enter new boat" />
            <button type="button" class="btn btn-danger btn-sm remove-field">X</button>
        `;
        const children = container.children;
        container.insertBefore(newField, children[children.length - 1]); // Keep the "+" button at the bottom
    }

    // Attach click event to 'Add Crew' buttons
    document.querySelectorAll('[id^=add-boat]').forEach(button => {
        button.addEventListener('click', function() {
            addNewCrewFields();
        });
    });

    // Attach click event to 'Remove' buttons inside the new crew fields
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-field')) {
            e.target.parentElement.remove();
        }
    });

    // Attach click event to 'Edit' buttons
    document.querySelectorAll('.edit-event').forEach(button => {
        button.addEventListener('click', function() {
            const date = button.getAttribute('data-date');
            const name = button.getAttribute('data-name');
            const type = button.getAttribute('data-type');
            const crews = button.getAttribute('data-crews').split(',');
            const event_id = button.getAttribute('data-id').split(',');

            // Populate the form with the event details
            document.getElementById('date').value = date;
            document.getElementById('name').value = name;
            document.getElementById('type').value = type;
            document.getElementById('event_id').value = event_id;

            // Clear existing crew fields but keep the "+" button
            const container = document.getElementById('new-boats');
            const addButton = container.lastChild; // Keep the "+" button

            // Clear all fields except the last (add button)
            while (container.children.length > 1) {
                container.firstChild.remove(); // Remove all except the add button
            }

            // Add crew fields from the event
            crews.forEach((crew, index) => {
                if (crew.trim()) {
                    if (index < container.children.length - 1) { // If there is an existing input
                        // Update the existing input
                        const existingField = container.children[index];
                        existingField.querySelector('input').value = crew.trim();
                    } else {
                        // Create a new field if there are fewer crews than input fields
                        addNewCrewFields();
                        const newField = container.children[index];
                        newField.querySelector('input').value = crew.trim();
                    }
                }
            });

            // Scroll to the "Add New Race or Event" section
            const addEventSection = document.querySelector('h3.mb-4.mt-4'); // Select the section header
            addEventSection.scrollIntoView({ behavior: 'smooth', block: 'start' }); // Smooth scroll to the section
        });
    });
});
