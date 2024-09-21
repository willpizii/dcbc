document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('boatSelect').addEventListener('change', function() {
        const boatName = this.value;
        const boatInfoDivs = document.querySelectorAll('.boatInfoDiv');
        const boatInfoTable = document.getElementById('boatInfoTable');
        const shellField = document.getElementById('shellField');
        const boatInfoBody = document.getElementById('boatInfoBody');
        const availDiv = document.querySelector('.availDiv');
        const dateInput = document.getElementById('dateInput');

        let subDetectedElement = document.getElementById('subDetected');
        let replacementsContainer = document.getElementById('replacementsContainer');

        if (boatName) {
            fetch('/get_boat_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ boat_name: boatName }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error(data.error);
                } else {
                    // Clear any existing rows and replacement inputs
                    boatInfoBody.innerHTML = '';
                    if (replacementsContainer) {
                        replacementsContainer.innerHTML = ''; // Clear previous replacements
                    }
                    subDetectedElement.style.display = 'none'; // Hide SUB DETECTED initially

                    // Add shell info
                    shellField.value = data.shell;

                    // Positions in order
                    const positions = ['cox', 'stroke', 'seven', 'six', 'five', 'four', 'three', 'two', 'bow'];

                    positions.forEach(position => {
                        if (data[position]) {
                            const row = document.createElement('tr');
                            const posCell = document.createElement('td');
                            const rowerCell = document.createElement('td');
                            const actionCell = document.createElement('td');
                            const toggleButton = document.createElement('button');

                            // Set the rower's name and crsid in the cell
                            posCell.textContent = position.charAt(0).toUpperCase() + position.slice(1);
                            rowerCell.textContent = data[position].name;
                            rowerCell.id = data[position].crsid; // Set the id to the CRSID

                            // Configure the toggle button
                            toggleButton.textContent = "Sub";
                            toggleButton.className = "btn btn-danger";
                            toggleButton.addEventListener('click', function() {
                                // Toggle the strikethrough class
                                if (rowerCell.style.textDecoration === 'line-through') {
                                    rowerCell.style.textDecoration = 'none';
                                    rowerCell.classList.remove('subbed');

                                    // Remove the corresponding replacement input
                                    const replacementInput = document.getElementById(`replacement-${data[position].crsid}`);
                                    if (replacementInput) {
                                        replacementsContainer.removeChild(replacementInput); // Remove the element
                                    }
                                } else {
                                    rowerCell.style.textDecoration = 'line-through';
                                    rowerCell.classList.add('subbed');

                                    // Add a replacement input when subbed
                                    const replacementDiv = document.createElement('div');
                                    replacementDiv.id = `replacement-${data[position].crsid}`; // Unique ID for the input
                                    replacementDiv.innerHTML = `<span>${data[position].name}</span> <input class="form-control" type="text" placeholder="Replacement Name">`;
                                    replacementsContainer.appendChild(replacementDiv);
                                }

                                // Check if there are any subbed cells
                                const anySubbed = document.querySelectorAll('.subbed').length > 0;
                                subDetectedElement.style.display = anySubbed ? 'block' : 'none';
                                replacementsContainer.style.display = anySubbed ? 'block' : 'none'; // Show replacements
                            });

                            // Append cells and button to the row
                            row.appendChild(posCell);
                            row.appendChild(rowerCell);
                            actionCell.appendChild(toggleButton);
                            row.appendChild(actionCell);
                            boatInfoBody.appendChild(row);
                        }
                    });

                    // Check availability if a date is selected
                    const selectedDate = dateInput.value;
                    if (selectedDate){
                        const availableCrsids = Array.from(boatInfoBody.querySelectorAll('td[id]')).map(cell => cell.id);
                        showAvailabilities(selectedDate, availableCrsids)

                    }

                }
            })
            .catch(error => console.error('Error:', error));

            // Show both divs and the table when a valid boat is selected
            boatInfoDivs.forEach(div => div.style.display = 'flex');
            boatInfoTable.style.display = 'table'; // Show the table

        } else {
            // Hide both divs and the table if the default option is selected
            boatInfoDivs.forEach(div => div.style.display = 'none');
            boatInfoTable.style.display = 'none';
            subDetectedElement.style.display = 'none'; // Hide SUB DETECTED
            if (replacementsContainer) {
                replacementsContainer.innerHTML = ''; // Clear replacements
                replacementsContainer.style.display = 'none'; // Hide replacements
            }
            availDiv.style.display = 'none';
        }
    });

    function showAvailabilities(selectedDate, availableCrsids){
        fetch('/check_availability', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ date: selectedDate }),
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errorData => {
                        throw new Error(errorData.error || 'Something went wrong');
                    });
                }
                return response.json();
            })
            .then(data => {
                // Clear previous table content
                const availDiv = document.querySelector('.availDiv');
                availDiv.innerHTML = '';

                const viewButton = document.createElement('button');
                viewButton.textContent = 'View Availability';
                viewButton.className = 'btn btn-primary mb-3';

                // Add event listener to the button to redirect with date parameter
                viewButton.addEventListener('click', function() {
                    window.location.href = `/captains/availability/view?date=${encodeURIComponent(selectedDate)}`;
                });

                availDiv.appendChild(viewButton);

                // Parse user_data
                const userData = JSON.parse(data.user_data);

                // Create the table
                const table = document.createElement('table');
                table.className = 'table table-bordered';
                const tableBody = document.createElement('tbody');

                // Populate the table with user data
                const crsidToNameMap = {};

                // Assuming you have a similar table structure for the crew
                const crewRows = document.querySelectorAll('#boatInfoTable tr'); // Adjust to your actual ID

                crewRows.forEach(row => {
                    const rowerCell = row.cells[1]; // Assuming the CRSID is set as an ID in the second cell

                    crsidToNameMap[rowerCell.id] = rowerCell.textContent; // Map CRSID to the name from the first cell

                });

                // Now build the availability table based on the CRSID from the crew table
                availableCrsids.forEach(crsid => {
                    const row = document.createElement('tr');

                    const nameCell = document.createElement('td');
                    nameCell.style.width = '70%';  // Set width of the name cell
                    nameCell.textContent = crsidToNameMap[crsid] || '';  // Get name from the map or leave blank

                    const availCell = document.createElement('td');
                    availCell.style.width = '30%';  // Set width of the availability cell availability from userData if it exists
                    availCell.className = userData[crsid] || 'unfilled';

                    row.appendChild(nameCell);
                    row.appendChild(availCell);
                    tableBody.appendChild(row);
                });

                table.appendChild(tableBody);
                availDiv.appendChild(table);
                availDiv.style.display = 'flex';
            })
            .catch(error => {
                // Handle error case here
                const availDiv = document.querySelector('.availDiv');
                availDiv.innerHTML = `<p class="text-danger">${error.message}</p>`;
                availDiv.style.display = 'flex';  // Ensure the availability div is visible

                // Add error class to the date input
                dateInput.classList.add('error');

                console.error('Error:', error);
            });
    }

    document.getElementById('dateInput').addEventListener('change', function() {
        const selectedDate = this.value;
        const availableCrsids = Array.from(boatInfoBody.querySelectorAll('td[id]')).map(cell => cell.id);

        if (selectedDate) {
            showAvailabilities(selectedDate, availableCrsids)
        }
    });
});

