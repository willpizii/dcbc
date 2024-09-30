document.addEventListener('DOMContentLoaded', function() {
    const outing = window.outing; // Pass this variable from your template
    const boatName = window.boatName; // Assuming you have boat_name available in the outing object

    // Call the function if outing is not 'new'
    if (outing !== 'new' && boatName) {
        populateRowers(boatName);
    }

    document.getElementById('boatSelect').addEventListener('change', function() {
        const boatName = this.value;
        populateRowers(boatName);
    });

    console.log('Selected Boat Name:', boatName); // Log the boat name

    function populateRowers(boatName) {
        const boatInfoDivs = document.querySelectorAll('.boatInfoDiv');
        const boatInfoTable = document.getElementById('boatInfoTable');
        const shellField = document.getElementById('shellField');
        const boatInfoBody = document.getElementById('boatInfoBody');
        const availDiv = document.querySelector('.availDiv');
        const dateInput = document.getElementById('dateInput');
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
                            toggleButton.addEventListener('click', function(event) {
                                event.preventDefault(); // Prevent form submission

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
                                    replacementDiv.innerHTML = `
                                        <span>${data[position].name}</span>
                                        <div style="display: flex; align-items: center;">
                                            <input class="form-control" type="text" placeholder="Replacement Name" name="sub-${data[position].crsid}" id="" style="margin-right: 8px;" />
                                            <button class="btn btn-outline-success" id="submit-${data[position].crsid}">✓</button>
                                        </div>
                                    `;

                                    replacementsContainer.appendChild(replacementDiv);

                                    // Handle submit button click
                                    const submitButton = document.getElementById(`submit-${data[position].crsid}`);
                                    submitButton.addEventListener('click', function(event) {
                                        event.preventDefault(); // Prevent form submission
                                        const inputField = replacementDiv.querySelector('input');
                                        const replacementName = inputField.value;
                                        const prevName = inputField.name;

                                        if (inputField.disabled) {
                                            // If the input is disabled, unlock it and reset the button
                                            inputField.disabled = false;
                                            inputField.value = ''; // Clear the input field
                                            submitButton.className = 'btn btn-outline-success';
                                            inputField.id = ''; // Clear the ID
                                            inputField.className = 'form-control';
                                            inputField.name = prevName;
                                            return; // Exit early to prevent sending a request
                                        }

                                        if (replacementName) {
                                            // Lock the input
                                            inputField.disabled = true;

                                            // Send request to Flask to find CRSID matching the replacement name
                                            fetch('/find_crsid', {
                                                method: 'POST',
                                                headers: {
                                                    'Content-Type': 'application/json',
                                                },
                                                body: JSON.stringify({ name: replacementName }),
                                            })
                                            .then(response => response.json())
                                            .then(data => {
                                                if (data.crsid) {
                                                    submitButton.className = 'btn btn-success';
                                                    submitButton.title = 'User found';
                                                    inputField.id = `sub-${data.crsid}`;
                                                    showAvailabilitiesSubs(dateInput.value);
                                                    inputField.name = `${prevName}-${data.crsid}`;
                                                } else {
                                                    submitButton.className = 'btn btn-warning';
                                                    submitButton.title = `User not found - saving as ${replacementName}`;
                                                    inputField.id = '';
                                                    inputField.className = 'form-control';
                                                    inputField.name = prevName;
                                                }
                                            })
                                            .catch(error => {
                                                console.error('Error:', error);
                                                // Change button class to btn-warning on error
                                                submitButton.className = 'btn btn-warning';
                                            });
                                        }
                                    });
                                }

                                // Check if there are any subbed cells
                                const anySubbed = document.querySelectorAll('.subbed').length > 0;
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
                        showAvailabilities(selectedDate, availableCrsids);
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
            if (replacementsContainer) {
                replacementsContainer.innerHTML = ''; // Clear replacements
                replacementsContainer.style.display = 'none'; // Hide replacements
            }
            availDiv.style.display = 'none';
        }
    }

    function showAvailabilities(selectedDate, availableCrsids){
        if (!selectedDate || isNaN(Date.parse(selectedDate))) {
            console.log('Invalid date selected, doing nothing.');
            return; // Exit the function if the date is invalid
        }

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
                // Clear previous table and other content
                const availDiv = document.querySelector('.availDiv');
                availDiv.innerHTML = '';

                const lightingTime = document.createElement('h5');
                lightingTime.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" class="bi bi-sunrise" viewBox="0 0 16 16"><path d="M7.646 1.146a.5.5 0 0 1 .708 0l1.5 1.5a.5.5 0 0 1-.708.708L8.5 2.707V4.5a.5.5 0 0 1-1 0V2.707l-.646.647a.5.5 0 1 1-.708-.708zM2.343 4.343a.5.5 0 0 1 .707 0l1.414 1.414a.5.5 0 0 1-.707.707L2.343 5.05a.5.5 0 0 1 0-.707m11.314 0a.5.5 0 0 1 0 .707l-1.414 1.414a.5.5 0 1 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0M8 7a3 3 0 0 1 2.599 4.5H5.4A3 3 0 0 1 8 7m3.71 4.5a4 4 0 1 0-7.418 0H.499a.5.5 0 0 0 0 1h15a.5.5 0 0 0 0-1h-3.79zM0 10a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2A.5.5 0 0 1 0 10m13 0a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2a.5.5 0 0 1-.5-.5"/></svg>: ${data.lighting_down} <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" class="bi bi-sunset" viewBox="0 0 16 16"><path d="M7.646 4.854a.5.5 0 0 0 .708 0l1.5-1.5a.5.5 0 0 0-.708-.708l-.646.647V1.5a.5.5 0 0 0-1 0v1.793l-.646-.647a.5.5 0 1 0-.708.708zm-5.303-.51a.5.5 0 0 1 .707 0l1.414 1.413a.5.5 0 0 1-.707.707L2.343 5.05a.5.5 0 0 1 0-.707zm11.314 0a.5.5 0 0 1 0 .706l-1.414 1.414a.5.5 0 1 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0zM8 7a3 3 0 0 1 2.599 4.5H5.4A3 3 0 0 1 8 7m3.71 4.5a4 4 0 1 0-7.418 0H.499a.5.5 0 0 0 0 1h15a.5.5 0 0 0 0-1h-3.79zM0 10a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2A.5.5 0 0 1 0 10m13 0a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2a.5.5 0 0 1-.5-.5"/></svg>: ${data.lighting_up}`;

                availDiv.appendChild(lightingTime);

                const viewButton = document.createElement('button');
                viewButton.textContent = 'View Availability';
                viewButton.className = 'btn btn-primary mb-3';

                // Add event listener to the button to redirect with date parameter
                viewButton.addEventListener('click', function() {
                    window.location.href = `/captains/availability/crew?date=${encodeURIComponent(selectedDate)}&crew=${encodeURIComponent(boatName)}`;
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
                    availCell.style.width = '30%';  // Set width of the availability cell

                    const crsidData = userData[crsid]; // Get the data for the CRsid
                    if (crsidData && crsidData.hasOwnProperty('state')) {
                        availCell.className = crsidData['state']; // Set the className to crsidData['state']
                    } else {
                        availCell.className = 'unfilled'; // Default to 'unfilled' if no state is found
                    }

                    if (crsidData && crsidData.hasOwnProperty('notes')) {
                        availCell.textContent = crsidData['notes']; // Set the className to crsidData['state']
                    }

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

    function showAvailabilitiesSubs(selectedDate) {

        if (!selectedDate || isNaN(Date.parse(selectedDate))) {
            console.log('Invalid date selected, doing nothing.');
            return; // Exit the function if the date is invalid
        }
        // Collect CRSID from all input fields with a specific naming convention
        const availableCrsids = Array.from(document.querySelectorAll('input[id^="sub-"]')) // Assuming CRSID inputs start with 'sub-'
            .map(input => input.id.replace('sub-', '')) // Remove the 'sub-' prefix to get the CRSID
            .filter(crsid => crsid); // Filter out any empty IDs

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
            // Parse user_data
            const userData = JSON.parse(data.user_data);

            // Loop through available CRsids
            availableCrsids.forEach(crsid => {
                const inputField = document.querySelector(`input[id="sub-${crsid}"]`);
                if (inputField) {
                    const crsidData = userData[crsid]; // Get the data for the CRsid
                    const availability = crsidData ? (crsidData['state'] || 'unfilled') : 'unfilled'; // Check if crsidData exists
                    inputField.className = `form-control ${availability}`; // Change the class of the input based on availability
                }
            });
        })
        .catch(error => {
            // Handle error case here
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

    document.getElementById('submitOuting').addEventListener('submit', function() {
        const disabledInputs = this.querySelectorAll('input:disabled');
        disabledInputs.forEach(input => {
            input.disabled = false; // Enable the input
        });
    });
});

