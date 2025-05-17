
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
    const hours = Array.from({ length: 15 }, (_, i) => `${String(i + 6).padStart(2, '0')}:00`); // Hours from 6 AM to 6 PM
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

    const [day, month, year] = startDate.split('/').map(Number);

    // Create a new UTC date with the parsed values
    const start = new Date(Date.UTC(year, month - 1, day)); // Forces it to UTC at midnight

    // Create the header row (days across the top)
    let headerRow = '<tr><th></th>'; // Start with an empty cell for the top-left corner
    for (let i = 0; i < days.length; i++) {
        // Create the UTC date for each day by adding i days to the start date
        const currentDay = new Date(start.getTime() + i * 24 * 60 * 60 * 1000); // Adds days in UTC milliseconds

        // Format the header as DD/MM using UTC methods
        const dayFormatted = String(currentDay.getUTCDate()).padStart(2, '0');
        const monthFormatted = String(currentDay.getUTCMonth() + 1).padStart(2, '0'); // Months are 0-based

        // Add each day of the week to the header
        headerRow += `<th>${days[i].slice(0, 3)} ${dayFormatted}/${monthFormatted}</th>`;
    }
    headerRow += '</tr>';
    calendarBody.innerHTML += headerRow; // Append the header row to the calendar body

    // Fill in the hours and their corresponding days
    for (let hour of hours) {
        let row = `<tr><th>${hour}</th>`; // Each row starts with the hour

        for (let i = 0; i < days.length; i++) {
            // Create the UTC date for each day by adding i days to the start date
            const currentDay = new Date(start.getTime() + i * 24 * 60 * 60 * 1000); // Adds days in UTC milliseconds

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

    document.getElementById('copyPreviousWeek').addEventListener('click', function () {
        const currentStartDate = parseDateString(weekSelector.value); // Get the current week's start date
        const previousWeekStartDate = new Date(currentStartDate);
        previousWeekStartDate.setDate(currentStartDate.getDate() - 7); // Get the start date of the previous week

        const prevWeekData = {}; // Will store states for the previous week

        // First, gather the previous week's data from the table cells
        document.querySelectorAll('td[data-date]').forEach(cell => {
            const cellDate = new Date(cell.dataset.date);
            if (cellDate >= previousWeekStartDate && cellDate < currentStartDate) {
                const formattedDate = cellDate.toISOString().split('T')[0];
                prevWeekData[formattedDate] = markedCells.get(formattedDate); // Store the cell's state
            }
        });

        const weekData = existingData;

        document.querySelectorAll('td[data-date]').forEach(cell => {
            const date = cell.dataset.date; // Get the date from data-date attribute

            // Separate the full date part (YYYY-MM-DD) and time part (HH:MM)
            const datePart = date.slice(0, 10); // 'YYYY-MM-DD'
            const timePart = date.slice(11); // 'HH:MM'

            // Parse the date part and time part as individual integers
            const [year, month, day] = datePart.split('-').map(Number);
            const [hour, minute] = timePart.split(':').map(Number);

            // Create the current date using UTC to avoid time zone issues
            const currentDate = new Date(Date.UTC(year, month - 1, day, hour, minute)); // month is 0-based

            // Store the original day before subtracting a week
            const originalUTCDate = new Date(currentDate);

            currentDate.setUTCDate(currentDate.getUTCDate() - 7);

            // Format the date as 'YYYY-MM-DD-HH:MM' using UTC methods
            const newYear = currentDate.getUTCFullYear();
            const newMonth = String(currentDate.getUTCMonth() + 1).padStart(2, '0'); // Months are 0-based
            const newDay = String(currentDate.getUTCDate()).padStart(2, '0');
            const newHours = String(currentDate.getUTCHours()).padStart(2, '0');
            const newMinutes = String(currentDate.getUTCMinutes()).padStart(2, '0');

            const previousWeekDate = `${newYear}-${newMonth}-${newDay}-${newHours}:${newMinutes}`;

            // Determine the cell's state based on existing data
            let currentState = 'available'; // Default state

            if (weekData['available'] && weekData['available'].includes(previousWeekDate)) {
                currentState = 'available';
            } else if (weekData['not-available'] && weekData['not-available'].includes(previousWeekDate)) {
                currentState = 'not-available';
            } else if (weekData['if-required'] && weekData['if-required'].includes(previousWeekDate)) {
                currentState = 'if-required';
            } else if (weekData['out-of-cam'] && weekData['out-of-cam'].includes(previousWeekDate)) {
                currentState = 'out-of-cam';
            }


            // Apply the determined state
            markedCells.set(date, currentState);
            cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
            cell.classList.add(currentState);
        });
    });

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

    let initialMarkedState = new Map(markedCells);
    let initialNotes = {};

    document.querySelectorAll('input.note-input').forEach(input => {
        initialNotes[input.name] = input.value;
    });

    function handleBeforeUnload(e) {
        let changed = false;

        if (initialMarkedState.size !== markedCells.size) {
            changed = true;
        } else {
            for (let [key, val] of markedCells.entries()) {
                if (initialMarkedState.get(key) !== val) {
                    changed = true;
                    break;
                }
            }
        }

        if (!changed) {
            document.querySelectorAll('input.note-input').forEach(input => {
                if ((initialNotes[input.name] || '') !== input.value) {
                    changed = true;
                }
            });
        }

        if (changed) {
            e.preventDefault();
            e.returnValue = '';
        }
    }

    window.addEventListener('beforeunload', handleBeforeUnload);

    form.addEventListener('submit', function () {
        window.removeEventListener('beforeunload', handleBeforeUnload);
    });
});
