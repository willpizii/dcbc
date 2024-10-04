let filteredData = [];
let usersList = [];

function filter() {
    // Get the values of each filter
    const squadFilter = document.getElementById('squadFilter').value;
    const tagFilter = document.getElementById('tagFilter').value;
    const crewFilter = document.getElementById('crewFilter').value;

    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;

    // Prepare data to send in the POST request
    const data = {
        squad: squadFilter,
        tag: tagFilter,
        crew: crewFilter,
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

    // Add a column for each user
    usersList.forEach(user => {
        const userHeader = document.createElement('th');
        userHeader.textContent = user.name;
        headerRow.appendChild(userHeader);
    });

    // Append the header row to the table
    table.appendChild(headerRow);

    // Create a row for each date in the availabilityData
    filteredData.forEach(entry => {
        const row = document.createElement('tr');

        // Create and append the date cell
        const dateCell = document.createElement('td');
        const date = new Date(entry.date); // Create a Date object
        const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
        const formattedDate = date.toLocaleDateString('en-US', options)
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

        // Append the row to the table
        table.appendChild(row);
    });
}
