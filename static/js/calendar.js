// Define the days of the week for column headers
const days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// Function to get the number of days in a month
function getDaysInMonth(month, year) {
    return new Date(year, month, 0).getDate();
}

// Function to get the day of the week the month starts on (0 = Sunday, 1 = Monday, etc.)
function getStartDayOfMonth(month, year) {
    const startDay = new Date(year, month - 1, 1).getDay();
    return (startDay === 0) ? 6 : startDay - 1;
}

// Function to populate the calendar based on the selected month
function populateCalendar() {
    const monthSelector = document.getElementById('monthSelector');
    const selectedMonth = parseInt(monthSelector.value);  // Get the selected month as an integer
    const monthName = new Date(0, selectedMonth - 1).toLocaleString('default', { month: 'long' });
    const calendarBody = document.getElementById('calendarBody');
    const year = new Date().getFullYear(); // Use the current year

    // Clear previous rows
    calendarBody.innerHTML = '';

    // Determine the number of days in the selected month
    const daysInMonth = getDaysInMonth(selectedMonth, year);

    // Get the start day of the month (0 = Sunday, 1 = Monday, etc.)
    const startDay = getStartDayOfMonth(selectedMonth, year);

    // Fill in the weeks and days
    let dayCounter = 1; // Keeps track of the day of the month

    // We might need to account for previous month's days to align the first day correctly
    let numberOfWeeks = Math.ceil((daysInMonth + startDay) / 7);

    for (let week = 0; week < numberOfWeeks; week++) {
        let row = '<tr>';

        for (let day = 0; day < 7; day++) {
            if (week === 0 && day < startDay || dayCounter > daysInMonth) {
                // Empty cell for days outside the current month
                row += '<td class="fill-grey"></td>';
            } else {
                // Construct the full YYYYMMDD date string
                let fullDate = `${year}${String(selectedMonth).padStart(2, '0')}${String(dayCounter).padStart(2, '0')}`;
                const noteValue = userNotes[fullDate] || "";
                row += `<td data-date="${fullDate}">${dayCounter}<input class='form-control note-input' input-date="${fullDate}" name="input-${fullDate}" value="${noteValue}" type="hidden" /></td>`;
                dayCounter++;
            }
        }

        row += '</tr>';
        calendarBody.innerHTML += row;
    }
}

// Initial population of the calendar
populateCalendar();

// Add event listener for month selector change
document.getElementById('monthSelector').addEventListener('change', populateCalendar);

document.addEventListener('DOMContentLoaded', function () {
    let isMouseDown = false;
    let startCell = null;
    const markedCells = new Map(); // Map to track cell state
    const lockedCells = new Set(); // Set to track locked cells

    let markMode = 'available'; // Default mode
    let currentMonth = document.getElementById('monthSelector').value;

    const table = document.getElementById('availabilityTable');
    const form = document.getElementById('availabilityForm');
    const monthSelector = document.getElementById('monthSelector');

    const existingData = window.existingData;
    const raceDays = window.raceDays;
    const eventDays = window.eventDays;

    // Function to update table based on week selection
    function initializeTable() {
        const selectedMonth = monthSelector.value;
        if (!existingData) {
            console.warn(`No data found`);
            document.querySelectorAll('td[data-date]').forEach(cell => {
                const date = cell.dataset.date;

                // Determine the cell's state based on existing data
                let currentState = 'available'; // Default state
                // Apply the determined state
                markedCells.set(date, currentState);
                cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
                cell.classList.add(currentState);
            });
            return;
        }

        const monthData = existingData;
        console.log(monthData);

        document.querySelectorAll('td[data-date]').forEach(cell => {
            const date = cell.dataset.date;

            // Determine the cell's state based on existing data
            let currentState = 'available'; // Default state

            if (monthData['available'] && monthData['available'].includes(date)) {
                currentState = 'available';
            } else if (monthData['not-available'] && monthData['not-available'].includes(date)) {
                currentState = 'not-available';
            } else if (monthData['if-required'] && monthData['if-required'].includes(date)) {
                currentState = 'if-required';
            } else if (monthData['out-of-cam'] && monthData['out-of-cam'].includes(date)) {
                currentState = 'out-of-cam';
            }

            if (raceDays && raceDays[date] && eventDays && eventDays[date]){
                cell.classList.add('race-event-day')
                cell.title = raceDays[date]+'\n'+eventDays[date];

                cell.onclick = function() {
                    window.location.href = '/races'; // Redirect to /races on click
                };
            } else if (raceDays && raceDays[date]) {
                cell.classList.add('race-day');
                cell.title = raceDays[date];

                cell.onclick = function() {
                    window.location.href = '/races'; // Redirect to /races on click
                };
            } else if (eventDays && eventDays[date]) {
                cell.classList.add('event-day');
                cell.title = eventDays[date];
            }

            // Apply the determined state
            markedCells.set(date, currentState);
            cell.classList.remove('available', 'not-available', 'if-required', 'out-of-cam');
            cell.classList.add(currentState);
        });
    }

    initializeTable();

    monthSelector.addEventListener('change', function() {
        currentMonth = monthSelector.value;
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
            month: currentMonth,
            times: times,
            notes: notes
        };

        console.log("Submitting data:", JSON.stringify(data)); // Debugging: Log the data being sent

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
