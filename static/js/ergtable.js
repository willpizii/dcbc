// Set default values to the next week from today's date
window.onload = function() {
    const today = new Date();
    const nextWeekStart = new Date();
    nextWeekStart.setDate(today.getDate() - 7); // A week ago
    const nextWeekEnd = new Date();
    nextWeekEnd.setDate(today.getDate() + 1); // Tomorrow (to include today!)

    document.getElementById('start_date').value = nextWeekStart.toISOString().split('T')[0];
    document.getElementById('end_date').value = nextWeekEnd.toISOString().split('T')[0];

    filter()
};

function filter() {
    const squadFilter = document.getElementById('squadFilter').value;
    const crewFilter = document.getElementById('crewFilter').value;
    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;

    const data = {
        squad: squadFilter,
        crew: crewFilter,
        start_date: startDate,
        end_date: endDate
    };

    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json(); // Expecting JSON response
    })
    .then(responseData => {
        console.log('Success:', responseData);
        generateTable(responseData); // Generate table with the new data
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}

function generateTable(data) {
    const tableBody = document.querySelector('#ergTable tbody');
    tableBody.innerHTML = ''; // Clear existing rows

    if (data.length === 0) {
        const noDataRow = document.createElement('tr');
        const noDataCell = document.createElement('td');
        noDataCell.colSpan = '100%'; // Adjust based on the number of columns
        noDataCell.textContent = 'No data available';
        noDataRow.appendChild(noDataCell);
        tableBody.appendChild(noDataRow);
        return;
    }

    data.forEach(item => {
        const row = document.createElement('tr');

        // Ensure to map the values correctly based on expected column structure
        const columns = ['user_id', 'type', 'date', 'time', 'distance', 'split', 'avghr', 'workout_type', 'spm', 'comments'];

        columns.forEach(col => {
            const cell = document.createElement('td');
            cell.textContent = item[col] !== null && item[col] !== 'unknown' && item[col] !== '' ? item[col] : '';
            row.appendChild(cell);
        });

        tableBody.appendChild(row);
    });
}
