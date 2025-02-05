let currentTableData = []; // To store fetched data for client-side filtering

// Set default values to the next week from today's date
window.onload = function() {
    const today = new Date();
    const nextWeekStart = new Date();
    nextWeekStart.setDate(today.getDate() - 7); // A week ago
    const nextWeekEnd = new Date();
    nextWeekEnd.setDate(today.getDate() + 1); // Tomorrow (to include today!)

    document.getElementById('start_date').value = nextWeekStart.toISOString().split('T')[0];
    document.getElementById('end_date').value = nextWeekEnd.toISOString().split('T')[0];

    filter(); // Initial data fetch
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
        return response.json();
    })
    .then(responseData => {
        console.log('Fetched Data:', responseData);
        currentTableData = responseData; // Store the fetched data
        generateTable(currentTableData); // Populate the table
        searchFilter(); // Apply the current search filter after populating
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
        noDataCell.colSpan = '10'; // Adjust based on the number of columns
        noDataCell.textContent = 'No data available';
        noDataCell.style.textAlign = 'center';
        noDataRow.appendChild(noDataCell);
        tableBody.appendChild(noDataRow);
        return;
    }

    data.forEach(item => {
        const row = document.createElement('tr');
        const columns = ['user_id', 'type', 'date', 'time', 'distance', 'split', 'avghr', 'workout_type', 'spm', 'comments'];

        columns.forEach(col => {
            const cell = document.createElement('td');
            cell.textContent = item[col] !== null && item[col] !== 'unknown' && item[col] !== '' ? item[col] : '';
            row.appendChild(cell);
        });

        tableBody.appendChild(row);
    });
}

function searchFilter() {
    const searchInput = document.getElementById('ergSearch').value.toLowerCase();
    const rows = document.querySelectorAll('#ergTable tbody tr');

    let visibleRowCount = 0;

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowText = Array.from(cells).map(cell => cell.textContent.toLowerCase()).join(' ');

        if (rowText.includes(searchInput)) {
            row.style.display = ''; // Show matching row
            visibleRowCount++;
        } else {
            row.style.display = 'none'; // Hide non-matching row
        }
    });

    const existingMessage = document.querySelector('#ergTable tbody .no-results');
    if (visibleRowCount === 0 && rows.length > 0) {
        if (!existingMessage) {
            const noDataRow = document.createElement('tr');
            noDataRow.classList.add('no-results');
            const noDataCell = document.createElement('td');
            noDataCell.colSpan = '10';
            noDataCell.textContent = 'No matching results';
            noDataCell.style.textAlign = 'center';
            noDataRow.appendChild(noDataCell);
            document.querySelector('#ergTable tbody').appendChild(noDataRow);
        }
    } else if (existingMessage) {
        existingMessage.remove();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('ergSearch').addEventListener('input', searchFilter);
});
