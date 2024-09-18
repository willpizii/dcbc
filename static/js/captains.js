document.addEventListener('DOMContentLoaded', function() {
    function filter() {
        var squadFilter = document.getElementById('squadFilter').value;
        var tagFilter = document.getElementById('tagFilter').value;
        var searchQuery = document.getElementById('nameSearch').value.toLowerCase();
        var rows = document.querySelectorAll('#userTableBody tr');

        rows.forEach(function(row) {
            // Check squad filter
            var squadMatch = (squadFilter === 'all' || row.classList.contains('squad-' + squadFilter));
            var isBoth = row.classList.contains('squad-both');

            // Check tag filter
            var tagMatch = tagFilter === 'all'; // Start with true if 'all' is selected
            if (tagFilter !== 'all') {
                var tags = row.querySelectorAll('[data-tag]');
                tagMatch = Array.from(tags).some(function(tagField) {
                    return tagField.getAttribute('data-tag').toLowerCase() === tagFilter.toLowerCase();
                });
            }

            // Check search query
            var nameCells = row.querySelectorAll('td:nth-child(2)'); // Name columns
            var nameMatch = Array.from(nameCells).some(function(cell) {
                return cell.textContent.toLowerCase().includes(searchQuery);
            });

            var tagCells = row.querySelectorAll('[data-tag]');
            var tagNameMatch = Array.from(tagCells).some(function(cell) {
                return cell.getAttribute('data-tag').toLowerCase().includes(searchQuery);
            });

            if ((squadMatch || isBoth) && tagMatch && (nameMatch || tagNameMatch)) {
                row.style.display = ''; // Show row if it matches all filters
            } else {
                row.style.display = 'none'; // Hide row
            }
        });
    }

    document.getElementById('squadFilter').addEventListener('change', filter);
    document.getElementById('tagFilter').addEventListener('change', filter);
    document.getElementById('nameSearch').addEventListener('input', filter);

    filter();

    document.querySelectorAll('.delete-tag').forEach(button => {
        button.addEventListener('click', function() {
            const crsid = this.getAttribute('data-crsid');
            const tag = this.getAttribute('data-tag');

            // Find the input field and delete button
            const tagDiv = this.parentElement;
            tagDiv.remove();

            // Optional: Use JavaScript to track changes on the client side
            // You might need to update the hidden form or handle the update in the backend

            // If you need to handle the changes in a hidden form or another way, you can do it here
        });
    });

    // Function to add new crew fields
    function addNewCrewFields(crsid) {
        const container = document.getElementById(`new-tags-${crsid}`);
        const newField = document.createElement('div');
        newField.className = 'd-flex align-items-center mb-1';
        newField.innerHTML = `
            <input type="text" name="tag_${crsid}[]" class="form-control me-2" placeholder="Enter new tag" />
            <button type="button" class="btn btn-danger btn-sm remove-field">Remove</button>
        `;
        container.appendChild(newField);
    }

    // Attach click event to 'Add Crew' buttons
    document.querySelectorAll('[id^=add-tag-]').forEach(button => {
        button.addEventListener('click', function() {
            const crsid = this.getAttribute('data-crsid');
            addNewCrewFields(crsid);
        });
    });

    // Attach click event to 'Remove' buttons inside the new crew fields
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-field')) {
            e.target.parentElement.remove();
        }
    });
});
