let filteredData = [];
let usersList = [];

function filter() {
    // Get the values of each filter
    const squadFilter = document.getElementById('squadFilter').value;
    const tagFilter = document.getElementById('tagFilter').value;
    const crewFilter = document.getElementById('crewFilter').value;
    const modeSwitch = document.getElementById('modeSwitch').value;

    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;

    // Prepare data to send in the POST request
    const data = {
        squad: squadFilter,
        tag: tagFilter,
        crew: crewFilter,
        mode: modeSwitch,
        start_date: startDate,
        end_date: endDate
    };

    // Send the POST request
    fetch(window.location.href, {  // POST to the current page
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)  // Send data as JSON
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(responseData => {
        filteredData = responseData.availability_data; // Store the filtered availability data
        usersList = responseData.users_list; // Store the users list
        console.log('Success:', filteredData, usersList);
        generateTable(filteredData, usersList); // Call generateTable with the new data
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}


// Set default values to the next week from today's date
window.onload = function() {
    const today = new Date();
    const nextWeekStart = new Date();
    nextWeekStart.setDate(today.getDate() + 1); // Tomorrow as start date
    const nextWeekEnd = new Date();
    nextWeekEnd.setDate(today.getDate() + 7); // One week from today as end date

    document.getElementById('start_date').value = nextWeekStart.toISOString().split('T')[0];
    document.getElementById('end_date').value = nextWeekEnd.toISOString().split('T')[0];

    filter()
};


function generateTable() {
    const table = document.getElementById('availabilityTable');

    // Clear previous table content
    table.innerHTML = '';

    // Create the header row
    const headerRow = document.createElement('tr');
    const dateHeader = document.createElement('th');
    dateHeader.textContent = 'Date';
    dateHeader.style.width = '200px';
    headerRow.appendChild(dateHeader);

    // Add a column for each user, with an “×” button
    usersList.forEach((user, i) => {
        const th = document.createElement('th');
        th.textContent = user.name;
        th.style.position = 'sticky';

        const btn = document.createElement('span');
        btn.textContent = '×';
        btn.style.position = 'absolute';
        btn.style.top = '0';
        btn.style.bottom = '0';
        btn.style.right = '4px';
        btn.style.width = '16px';
        btn.style.display = 'flex';
        btn.style.alignItems = 'center';
        btn.style.justifyContent = 'center';
        btn.style.cursor = 'pointer';
        btn.style.fontSize = '0.75rem';
        btn.style.lineHeight = '1';
        btn.dataset.col = i + 1;
        btn.onclick = () => hideColumn(Number(btn.dataset.col));

        th.appendChild(btn);
        headerRow.appendChild(th);
    });
    table.appendChild(headerRow);


    let previousDay = null; // To track the previous day

    // Create a row for each date in the availabilityData
    filteredData.forEach(entry => {
        const row = document.createElement('tr');

        // Create and append the date cell
        const dateCell = document.createElement('td');
        let date, formattedDate;

        if (document.getElementById('modeSwitch').value === 'daily') {
            date = new Date(entry.date); // Create a Date object
            const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
            formattedDate = date.toLocaleDateString('en-US', options);
        } else {
            date = new Date(entry.date); // Create a Date object

            // Format as HH:MM DD/MM/YYYY using UTC methods
            const hours = String(date.getUTCHours()).padStart(2, '0');
            const minutes = String(date.getUTCMinutes()).padStart(2, '0');
            const day = String(date.getUTCDate()).padStart(2, '0');
            const month = date.toLocaleDateString('en-GB', { month: 'short' }); // Short month format

            // Add weekday short string using UTC methods
            const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const weekday = weekdays[date.getUTCDay()]; // Get the UTC weekday short string

            // Combine to the desired format: 'Weekday HH:MM DD MMM'
            formattedDate = `${weekday} ${day} ${month} ${hours}:${minutes} `;

            // Check if the current UTC day is different from the previous UTC day
            const currentDay = date.getUTCDate(); // Get the current day in UTC

            if (previousDay !== null && previousDay !== currentDay) {
                // Add an empty row or divider line between different days
                const dividerRow = document.createElement('tr');
                const dividerCell = document.createElement('td');
                dividerCell.colSpan = usersList.length + 1; // Span across all columns
                dividerCell.style.borderTop = '2px solid #000'; // Strong divider line
                dividerCell.style.borderBottom = '2px solid #000'; // Strong divider line
                dividerRow.appendChild(dividerCell);
                table.appendChild(dividerRow); // Append divider row to the table
            }

            // Update previousDay with the current day after the check
            previousDay = currentDay;
        }
        dateCell.textContent = formattedDate;
        row.appendChild(dateCell);

        const userData = JSON.parse(entry.user_data);

        // Create and append user availability cells
        usersList.forEach(user => {
            const availabilityCell = document.createElement('td');
            const userAvailability = userData[user.crsid]?.state || 'Nodata'; // Access availability
            availabilityCell.className = userAvailability;
            const userNotes = userData[user.crsid]?.notes || ''; // Access availability
            availabilityCell.textContent = userNotes;
            availabilityCell.style.minWidth = '80px';

            row.appendChild(availabilityCell);
        });

        // Append the row to the calendar body
        table.appendChild(row);
    });
}

function toggleEmptyColumns() {
  const btn = document.getElementById('toggleEmptyCols');
  const hide = btn.getAttribute('data-hidden') === 'false';
  const table = document.getElementById('availabilityTable');
  const headerCells = table.querySelectorAll('tr:first-child th');
  const rows = Array.from(table.querySelectorAll('tr')).slice(1);

  headerCells.forEach((th, colIndex) => {
    if (colIndex === 0) return;

    let shouldToggle = true;
    if (hide) {
      const dataRows = rows.filter(r => r.children.length > headerCells.length - 1);
      shouldToggle = dataRows.every(row =>
        row.children[colIndex].classList.contains('Nodata')
      );
    }

    const display = hide && shouldToggle ? 'none' : '';
    th.style.display = display;
    rows.forEach(row => {
      if (row.children[colIndex]) {
        row.children[colIndex].style.display = display;
      }
    });
  });

  btn.textContent = hide ? 'Show Empty Users' : 'Hide Empty Users';
  btn.setAttribute('data-hidden', hide ? 'true' : 'false');
}

function hideColumn(colIndex) {
  const table = document.getElementById('availabilityTable');
  const rows = table.querySelectorAll('tr');
  rows.forEach(row => {
    const cell = row.children[colIndex];
    if (cell) cell.style.display = 'none';
  });
}

function resetColumns() {
  const table = document.getElementById('availabilityTable');
  const rows = table.querySelectorAll('tr');
  const maxCols = rows[0].children.length;
  rows.forEach(row => {
    for (let c = 0; c < maxCols; c++) {
      if (row.children[c]) row.children[c].style.display = '';
    }
  });
}
