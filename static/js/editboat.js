// Get the boatType from the backend (passed from Python or fallback)
const selectedType = window.selectedType;

// Find the select element
const boatTypeSelect = document.getElementById('boatType');

// Set the default selected value based on the selectedType
if (boatTypeSelect) {
    boatTypeSelect.value = selectedType; // Set the value to selectedType if it exists
}

const boatsData = {
    'eight': ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow'],
    'coxed-four': ['cox', 'stroke', 'three', 'two', 'bow'],
    'coxless-four': ['stroke', 'three', 'two', 'bow'],
    'pair': ['stroke', 'bow']
};

const defaultSide = {
    'eight': ['cox', 'stroke', 'bow', 'stroke', 'bow', 'stroke', 'bow', 'stroke', 'bow'],
    'coxed-four': ['cox', 'stroke', 'bow', 'stroke', 'bow'],
    'coxless-four': ['stroke', 'bow', 'stroke', 'bow'],
    'pair': ['stroke', 'bow']
};

const boatsList = window.boatsList;

const user_list = window.user_list;

function filter() {
    const boatType = document.getElementById('boatType').value;

    const positions = boatsData[boatType]; // Get the positions for the selected boat type
    const defSides = defaultSide[boatType]; // Get the positions for the selected boat type
    const tableBody = document.getElementById('userTableBody');

    // Clear existing rows
    tableBody.innerHTML = '';

    // Add rows for the selected boat type
    positions.forEach((position, index) => {
        const side = defSides[index]; // Get the default side for this position
        const row = document.createElement('tr');

        // Create the select element for assigning users
        const userOptions = Object.keys(user_list)
            .map(crsid => `<option value="${crsid}">${user_list[crsid]}</option>`)
            .join(''); // Generate options from user_list

        if (position === 'cox') {
            row.innerHTML = `
                <td>${position}</td>
                <td>
                    <input type="text" class="form-control" value="Cox" name="side-${position}" readonly disabled/>
                    <input type="text" class="form-control" value="cox" name="side-${position}" readonly hidden/>
                </td>
                <td><div class="d-flex">
                    <select class="form-select row-select me-2" id="seat-${position}" name="seat-${position}">
                        <option value="None" selected disabled hidden>Select Cox</option>
                        ${userOptions} <!-- User list as options -->
                    </select><button class="btn btn-success" type="button">↺</button>
                </div></td>
            `;
        } else {
            row.innerHTML = `
                <td>${position}</td>
                <td>
                    <select id="switchSide" class="form-select" name="side-${position}">
                        <option value="stroke" ${side === 'stroke' ? 'selected' : ''}>Stroke</option>
                        <option value="bow" ${side === 'bow' ? 'selected' : ''}>Bow</option>
                    </select>
                </td>
                <td><div class="d-flex">
                    <select class="form-select row-select me-2" id="seat-${position}" name="seat-${position}">
                        <option value="None" selected disabled hidden>Select Rower</option>
                        ${userOptions} <!-- User list as options -->
                    </select><button class="btn btn-success reset-btn" type="button">↺</button>
                </div></td>
            `;
        }
        tableBody.appendChild(row);

        const seat = document.getElementById(`seat-${position}`);
        if (boatsList[position]) {
            seat.value = boatsList[position]; // Set the value to selectedType if it exists
        }

        toggleResetButton(seat);
        updateSelectOptions();
    });

    attachEventListeners();

    updateSelectOptions();

}

// Initialize table when page loads
document.addEventListener('DOMContentLoaded', function() {
    filter(); // Call filter to render the default selection
    attachEventListeners();

    updateSelectOptions();
});

function attachEventListeners() {
    // Add event listeners to all selects to update options when changed
    document.querySelectorAll('select.row-select').forEach(select => {
        select.addEventListener('change', updateSelectOptions);
        toggleResetButton(select);
    });

    // Add event listeners to all reset buttons
    document.querySelectorAll('.btn-success').forEach(button => {
        button.addEventListener('click', function() {
            resetSelect(this);
        });
    });
}

function toggleResetButton(selectElement) {
    const resetButton = selectElement.nextElementSibling; // Get the reset button next to the select box
    if (selectElement.value === 'None') {
        resetButton.style.display = 'none'; // Hide the button if the selected value is None
    } else {
        resetButton.style.display = 'inline'; // Show the button if a valid rower is selected
    }
}

function resetSelect(button) {
    // Get the select element within the same table cell as the clicked button
    const select = button.previousElementSibling;
    const previousValue = select.value;
    select.value = 'None'; // Set select to the default value
    toggleResetButton(select); // Hide the reset button again

    // Remove the previously selected value from the global list
    if (previousValue !== 'None') {
        selectedValues = selectedValues.filter(value => value !== previousValue);
        updateSelectOptions();
    }
}

function updateSelectOptions() {
    // Get all select elements
    const selects = document.querySelectorAll('select.row-select');

    // Clear previous selections
    selectedValues = [];

    // Collect current selected values
    selects.forEach(select => {
        const value = select.value;
        if (value !== 'None') {
            selectedValues.push(value);
        }
    });

    // Update options in each select element
    selects.forEach(select => {
        const options = select.querySelectorAll('option');
        options.forEach(option => {
            const isDisabled = selectedValues.includes(option.value) && option.value !== select.value;
            option.style.display = isDisabled ? 'none' : '';
        });
        toggleResetButton(select);
    });
}

// Initialize with an empty list of selected values
let selectedValues = [];

document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to all selects to update options when changed
    document.querySelectorAll('select.row-select').forEach(select => {
        select.addEventListener('change', updateSelectOptions);
        toggleResetButton(select);
    });

    // Initialize the options when page loads
    updateSelectOptions();

    // Add event listeners to all reset buttons
    document.querySelectorAll('.btn-success').forEach(button => {
        button.addEventListener('click', function() {
            resetSelect(this);
        });
    });
});

document.getElementById('boatForm').onsubmit = function(event) {
    const boatNameInput = document.getElementById('boat_name');
    if (!boatNameInput.value.trim()) {
        event.preventDefault(); // Prevent form submission
        alert('Please enter a boat name.');
    }
};
