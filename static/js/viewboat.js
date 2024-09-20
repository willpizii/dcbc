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
                    <input type="text" class="form-control" value="cox" name="side-${position}" readonly disabled/>
                </td>
                <td><div class="d-flex">
                    <input type="text" class="form-control row-select me-2" id="seat-${position}" name="seat-${position}" disabled>
                </div></td>
            `;
        } else {
            row.innerHTML = `
                <td>${position}</td>
                <td>
                    <input id="switchSide" class="form-control" name="side-${position}" disabled value="${side === 'stroke' ? 'stroke' : 'bow'}" />
                </td>
                <td><div class="d-flex">
                    <input type="text" class="form-control row-select me-2" id="seat-${position}" name="seat-${position}" disabled>
                </div></td>
            `;
        }
        tableBody.appendChild(row);

        const seat = document.getElementById(`seat-${position}`);
        if (boatsList[position]) {
            seat.value = user_list[boatsList[position]]; // Set the input value based on the crsid in boatsList
        }
    });


}

// Initialize table when page loads
document.addEventListener('DOMContentLoaded', function() {
    filter(); // Call filter to render the default selection
});



