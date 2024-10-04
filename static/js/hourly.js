
function parseDateString(dateString) {
    // Split the date string into parts
    const parts = dateString.split('/');
    // Create a new Date object with year, month (0-indexed), and day
    return new Date(parts[2], parts[1] - 1, parts[0]); // Month is 0-based
}

function populateWeeklyHours(startDate) {
    const calendarBody = document.getElementById('calendarBody');

    // Clear previous rows
    calendarBody.innerHTML = '';

    // Define hours and days
    const hours = Array.from({ length: 13 }, (_, i) => `${String(i + 6).padStart(2, '0')}:00`); // Hours from 6 AM to 6 PM
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

    // Convert startDate to a Date object using the parseDateString function
    const start = parseDateString(startDate);

    // Create the header row (days across the top)
    let headerRow = '<tr><th></th>'; // Start with an empty cell for the top-left corner
    for (let i = 0; i < days.length; i++) {
        // Create a new date for the current day
        const currentDay = new Date(start);
        currentDay.setDate(start.getDate() + i); // Increment the date

        // Format the header as DD/MM
        const dayFormatted = String(currentDay.getDate()).padStart(2, '0');
        const monthFormatted = String(currentDay.getMonth() + 1).padStart(2, '0'); // Months are 0-based

        // Add each day of the week to the header
        headerRow += `<th>${days[i].slice(0, 3)} ${dayFormatted}/${monthFormatted}</th>`;
    }
    headerRow += '</tr>';
    calendarBody.innerHTML += headerRow; // Append the header row to the calendar body

    // Fill in the hours and their corresponding days
    for (let hour of hours) {
        let row = `<tr><th>${hour}</th>`; // Each row starts with the hour

        for (let i = 0; i < days.length; i++) {
            // Create a new date for the current day
            const currentDay = new Date(start);
            currentDay.setDate(start.getDate() + i); // Increment the date

            // Format the date as YYYY-MM-DD for the data attributes
            const dateString = currentDay.toISOString().split('T')[0];

            // Add a cell for each day of the week with the hour
            const noteValue = userNotes[`${dateString}-${hour}`] || "";
            row += `<td data-date="${dateString}-${hour}">${hour}<input class='form-control note-input' name="input-${dateString}-${hour}" value="${noteValue}" type="hidden" /></td>`;
        }

        row += '</tr>';
        calendarBody.innerHTML += row; // Append the row to the calendar body
    }
}

// Event listener for the weekSelector to repopulate the table when changed
document.getElementById('weekSelector').addEventListener('change', function () {
    const selectedStartDate = this.value; // Get the new Monday date in DD/MM/YYYY format
    populateWeeklyHours(selectedStartDate); // Repopulate the calendar
});

// Event listener for the weekSelector to repopulate the table when changed
document.getElementById('weekSelector').addEventListener('change', function () {
    const selectedStartDate = this.value; // Get the new Monday date
    populateWeeklyHours(selectedStartDate); // Repopulate the calendar
});


populateWeeklyHours(document.getElementById('weekSelector').value);

document.addEventListener('DOMContentLoaded', function () {
    let isMouseDown = false;
    let startCell = null;
    const markedCells = new Map(); // Map to track cell state
    const lockedCells = new Set(); // Set to track locked cells

    let markMode = 'available'; // Default mode
    const weekSelector = document.getElementById('weekSelector');
    const table = document.getElementById('availabilityTable');
    const form = document.getElementById('availabilityForm');

    const existingData = window.existingData || null; // Assume existingData is passed from backend
    const raceDays = window.raceDays || {};
    const eventDays = window.eventDays || {};

    // Function to update table based on week selection
    function initializeTable() {

        console.log(existingData);

        if (!existingData  || (typeof existingData === 'object' && Object.keys(existingData).length === 0)) {
            console.warn(`No data found, setting all cells to available.`);
            // Select all cells and set them to 'available'
            document.querySelectorAll('td[data-date]').forEach(cell => {
                const date = cell.dataset.date;

                // Set the default state to 'available'
                markedCells.set(date, 'available');
                cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
                cell.classList.add('available'); // Set all cells to 'available'
            });
            return; // Exit early if no existing data
        }

        const weekData = existingData;

        document.querySelectorAll('td[data-date]').forEach(cell => {
            const date = cell.dataset.date;

            // Determine the cell's state based on existing data
            let currentState = 'available'; // Default state

            if (weekData['available'] && weekData['available'].includes(date)) {
                currentState = 'available';
            } else if (weekData['not-available'] && weekData['not-available'].includes(date)) {
                currentState = 'not-available';
            } else if (weekData['if-required'] && weekData['if-required'].includes(date)) {
                currentState = 'if-required';
            } else if (weekData['out-of-cam'] && weekData['out-of-cam'].includes(date)) {
                currentState = 'out-of-cam';
            }

            // Apply the determined state
            markedCells.set(date, currentState);
            cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
            cell.classList.add(currentState);
        });
    }

    initializeTable();

    weekSelector.addEventListener('change', function() {
        markedCells.clear(); // Prevent submission of prior months which will wipe notes
        initializeTable();
    });

    // Event listeners for buttons
    const buttons = document.querySelectorAll('.button-group button');

    document.getElementById('markAvailable').addEventListener('click', function() {
        markMode = 'available';
        highlightButton(this);
    });

    document.getElementById('markNotAvailable').addEventListener('click', function() {
        markMode = 'not-available';
        highlightButton(this);
    });

    document.getElementById('markIfRequired').addEventListener('click', function() {
        markMode = 'if-required';
        highlightButton(this);
    });

    document.getElementById('markOutOfCam').addEventListener('click', function() {
        markMode = 'out-of-cam';
        highlightButton(this);
    });

    function highlightButton(activeButton) {
        buttons.forEach(button => button.classList.remove('active-button'));
        activeButton.classList.add('active-button');
    }

    table.addEventListener('mousedown', function (event) {
        if (event.target.tagName === 'TD' && event.target.dataset.date) {
            isMouseDown = true;
            startCell = event.target;
            toggleCell(event.target);
        }
    });

    table.addEventListener('mouseover', function (event) {
        if (isMouseDown && event.target.tagName === 'TD' && event.target.dataset.date) {
            if (startCell) {
                if (!lockedCells.has(event.target.dataset.date)) {
                    selectRectangle(startCell, event.target);
                }
            }
        }
    });

    document.addEventListener('mouseup', function () {
        isMouseDown = false;
        startCell = null;
        lockedCells.clear(); // Clear the lockedCells set when mouse is lifted
    });

    form.addEventListener('submit', function (event) {
        event.preventDefault(); // Prevent the default form submission
        const times = [];
        const notes = {};

        markedCells.forEach((state, date) => {
            if (state) {
                times.push(`${date}|${state}`);

                const noteInput = document.querySelector(`input[name="input-${date}"]`);
                if (noteInput) {
                    const noteValue = noteInput.value.trim(); // Trim whitespace from the input value
                    if (noteValue) { // Check if the note is not empty
                        notes[date] = noteValue; // Store note if it is not empty
                    }
                }
            }
        });

        const data = {
            name: form.name.value,
            weekStart: weekSelector.value,
            times: times,
            notes: notes
        };

        const xhr = new XMLHttpRequest();
        xhr.open("POST", form.action, true);
        xhr.setRequestHeader('Content-Type', 'application/json;charset=UTF-8');

        xhr.onload = function () {
            if (xhr.status === 200) {
                window.location.href = xhr.responseURL;
            } else {
                console.error("Submission failed with status:", xhr.status);
                console.error("Response text:", xhr.responseText);
                alert("An error occurred. Please try again.");
            }
        };

        xhr.onerror = function () {
            console.error("Request failed.");
            alert("Failed to send data. Please check your network connection.");
        };

        xhr.send(JSON.stringify(data));
    });

    function toggleCell(cell) {
        const date = cell.dataset.date;
        const currentState = markedCells.get(date);

        if (currentState !== markMode) {
            markedCells.set(date, markMode);
            cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
            cell.classList.add(markMode);
        }
    }

    function selectRectangle(start, end) {
        const startRow = start.parentElement.rowIndex;
        const startCol = start.cellIndex;
        const endRow = end.parentElement.rowIndex;
        const endCol = end.cellIndex;

        // Define the boundaries of the selection
        const minRow = Math.min(startRow, endRow);
        const maxRow = Math.max(startRow, endRow);
        const minCol = Math.min(startCol, endCol);
        const maxCol = Math.max(startCol, endCol);

        // Iterate through the cells within the defined rectangle
        for (let i = minRow; i <= maxRow; i++) {
            for (let j = minCol; j <= maxCol; j++) {
                const cell = table.rows[i].cells[j];
                if (cell.dataset.date && !lockedCells.has(cell.dataset.date)) {
                    toggleCell(cell);
                }
            }
        }
    }

    document.getElementById('showNotes').addEventListener('click', function(event) {
        event.preventDefault();
        // Select all note input elements
        const hiddenInputs = document.querySelectorAll('input.note-input');

        // Check if there are any hidden inputs
        if (hiddenInputs.length === 0) {
            console.log("No note inputs available.");
            return; // Exit the function if no inputs are found
        }

        // Check if the first hidden input is currently hidden
        const isVisible = hiddenInputs[0].type === 'text';

        // Toggle the input type between 'hidden' and 'text'
        hiddenInputs.forEach(function(input) {
            input.type = isVisible ? 'hidden' : 'text';  // Change the input type accordingly
        });
    });
});
