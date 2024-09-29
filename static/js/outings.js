const races = window.races;

// Function to add races to each day div
function addRacesToDay(dayDiv, dayName, races) {
    // Filter the races that match the day
    const dayRaces = races.filter(race => {
        const raceDate = new Date(race.date);
        const raceDayName = raceDate.toLocaleString('en-US', { weekday: 'long' });
        return raceDayName === dayName;
    });

    // If there are races for the day, create a section for them
    if (dayRaces.length > 0) {
        dayRaces.forEach(race => {
            const raceInfo = document.createElement('div');
            raceInfo.classList.add('race-info', 'mb-2', 'card');

            // Set border color based on race type
            if (race.type === 'Race') {
                raceInfo.style.borderColor = '#bb0088'; // Border for race
            } else if (race.type === 'Event') {
                raceInfo.style.borderColor = '#0088bb'; // Border for event
            }

            raceInfo.innerHTML = `
                <h5 class='card-title card-header'>${race.name}</h5>
                <i>${race.crews.split(',').join(', ')}</i>
            `;

            dayDiv.appendChild(raceInfo);
        });
    }
}

// Assuming you have a structure similar to this for your outings
const outingsByDay = {
    Monday: [],
    Tuesday: [],
    Wednesday: [],
    Thursday: [],
    Friday: [],
    Saturday: [],
    Sunday: [],
};

const yourOutings = window.yourOutings; // Pass from Flask
const subOutings = window.subOutings;   // Pass from Flask
const otherOutings = window.otherOutings;   // Pass from Flask

// Function to add outings to outingsByDay
function addOutings(outings, outingsByDay, outingType) {
    outings.forEach(outing => {
        const outingDate = new Date(outing.date_time);
        const dayName = outingDate.toLocaleString('en-US', { weekday: 'long' });

        if (outingType === 'your') {
            outing.type = 'your';
        } else if (outingType === 'sub') {
            outing.type = 'sub';
        } else {
            outing.type = 'other';
        }

        // Add outing to the correct day
        outingsByDay[dayName].push(outing);
    });
}

// Fill outingsByDay with data from all three sources
addOutings(yourOutings, outingsByDay, 'your');
addOutings(subOutings, outingsByDay, 'sub');
addOutings(otherOutings, outingsByDay, 'other');

// Calculate the dates for the week starting from fromDate
const fromDate = window.fromDate; // Ensure this is set correctly in your template
const dayNames = Object.keys(outingsByDay);
const weekDates = dayNames.map((day, index) => {
    const date = new Date(fromDate); // Clone fromDate
    date.setDate(fromDate.getDate() + index); // Increment the date by index
    return date.toLocaleDateString(); // Return formatted date
});

dayNames.forEach((day, index) => {
    const dayDiv = document.querySelector(`[data-day="${day}"]`);

    if (dayDiv) {
        // Create an h3 element for the day and date using only the first three characters of the day
        const header = document.createElement('h3');
        const shortDayName = day.substring(0, 3); // Get the first three characters of the day
        header.innerText = `${shortDayName} ${weekDates[index].split('/').slice(0, 2).join('/')}`; // Format date as DD/MM

        // Clear any existing content in the dayDiv and append the header
        dayDiv.innerHTML = ''; // Clear existing content
        dayDiv.appendChild(header); // Append the h3 header

        // Add races below the header
        addRacesToDay(dayDiv, day, races);

        let visibleOutingsCount = 0; // Track visible outings count for the day

        if (outingsByDay[day].length === 0) {
            // No outings message
            drawNoOutingsMessage(dayDiv);
        } else {
            outingsByDay[day].forEach(outing => {
                // Determine visibility based on outing type and selected filter
                const shouldShowOuting = outing.type !== 'other' || document.querySelector("#allOutingsCheck").checked;

                // Create a card for outing info with different styles based on outing type
                const outingInfo = document.createElement('div');
                outingInfo.style.display = shouldShowOuting ? 'block' : 'none'; // Toggle visibility based on filter

                if (outing.type === 'your') {
                    outingInfo.classList.add('card', 'border', 'mb-3', 'mt-2', 'mx-1'); // Your outing style
                } else if (outing.type === 'sub') {
                    outingInfo.classList.add('card', 'mb-3', 'mt-2', 'mx-1'); // Sub outing style (yellow border)
                } else {
                    outingInfo.classList.add('card', 'border', 'text-secondary', 'mb-3', 'mt-2', 'mx-1', 'other-outing'); // Other outing style (light background)
                }

                // Create the card body
                const cardBody = document.createElement('div');

                const headerStyle = outing.type === 'your' ? 'background-color: #bb0088; color: white;' : '';

                // Create content for the outing with icons and table for data
                cardBody.innerHTML = `
                    <a href="/outing?id=${outing.outing_id}" style="text-decoration: none; color: inherit;"><h4 class="card-header" style="${headerStyle}">${new Date(outing.date_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ${outing.time_type}</h4></a>
                    <div class="card-body">
                        <table style="width: 100%; border-collapse: collapse; text-align: left;">
                            <tr><td><strong>Crew:</strong></td><td>${outing.boat_name}</td></tr>
                            <tr><td><strong>Coach:</strong></td><td>${outing.coach}</td></tr>
                            ${outing.notes ? `<tr><td><strong>Notes:</strong></td><td>${outing.notes}</td></tr>` : ''}
                        </table>
                    </div>
                    ${outing.type === 'sub' ? '<div class="card-footer"><i>Subbed Outing</i></div>' : ''}
                `;

                // Append card body to the outing info card
                outingInfo.appendChild(cardBody);

                // Append outing info to the day div
                dayDiv.appendChild(outingInfo);

                if (shouldShowOuting) {
                    visibleOutingsCount++; // Increment visible outings count
                }
            });

            // If no outings are visible after filtering, show the "No outings for this day" message
            if (visibleOutingsCount === 0) {
                drawNoOutingsMessage(dayDiv);
            }
        }
    }
});

// Function to toggle visibility of 'other' outings
function toggleOtherOutings(showOther) {
    dayNames.forEach(day => {
        const dayDiv = document.querySelector(`[data-day="${day}"]`);
        if (dayDiv) {
            const outingCards = dayDiv.querySelectorAll('.other-outing');
            outingCards.forEach(card => {
                card.style.display = showOther ? 'block' : 'none'; // Toggle visibility of 'other' outings
            });

            // Remove any existing 'No outings on this day' message
            const existingNoOutingsMessage = dayDiv.querySelector('.no-outings-message');
            if (existingNoOutingsMessage) {
                existingNoOutingsMessage.remove();
            }

            // After toggling, check if any outings remain visible. If not, show the 'No outings' message.
            const visibleCards = dayDiv.querySelectorAll('.card:not([style*="display: none"])');
            if (visibleCards.length === 0) {
                drawNoOutingsMessage(dayDiv);
            }
        }
    });
}


// Function to draw the 'No outings for this day' message
function drawNoOutingsMessage(dayDiv) {
    // Remove any existing message first
    const existingMessage = dayDiv.querySelector('.no-outings-message');
    if (existingMessage) {
        existingMessage.remove();
    }

    const noOutingsMessage = document.createElement('div');
    noOutingsMessage.innerText = ' No outings on this day';
    noOutingsMessage.classList.add('text-danger', 'font-weight-bold', 'p-3', 'text-center', 'mt-2', 'no-outings-message'); // Added unique class for future removal

    const icon = document.createElement('i');
    icon.classList.add('fas', 'fa-times-circle', 'mr-2'); // Font Awesome icon
    noOutingsMessage.prepend(icon);

    dayDiv.appendChild(noOutingsMessage);
}

// Event listeners for radio buttons
document.getElementById('allOutingsCheck').addEventListener('change', function() {
    if (this.checked) {
        toggleOtherOutings(true); // Show 'other' outings when "All Outings" is selected
    }
});

document.getElementById('myOutingsCheck').addEventListener('change', function() {
    if (this.checked) {
        toggleOtherOutings(false); // Hide 'other' outings when "My Outings" is selected
    }
});

// Initially hide 'other' outings since 'My Outings' is checked by default
toggleOtherOutings(false);

document.getElementById('nextWeekButton').addEventListener('click', function() {
    // Get the value of the date input
    const fromDate = new Date(document.getElementById('fromDateBox').value);

    // Add 7 days to the date
    fromDate.setDate(fromDate.getDate() + 7);

    // Format the date to YYYY-MM-DD
    const nextWeekDate = fromDate.toISOString().split('T')[0];

    // Redirect to /outings with the weekof parameter
    window.location.href = `/outings?weekof=${nextWeekDate}`;
});
document.getElementById('previousWeekButton').addEventListener('click', function() {
    // Get the value of the date input
    const fromDate = new Date(document.getElementById('fromDateBox').value);

    // Subtract 7 days from the date
    fromDate.setDate(fromDate.getDate() - 7);

    // Format the date to YYYY-MM-DD
    const previousWeekDate = fromDate.toISOString().split('T')[0];

    // Redirect to /outings with the weekof parameter
    window.location.href = `/outings?weekof=${previousWeekDate}`;
});

// Function to filter outings based on input text
function filterOutings(searchText) {
    const showOtherOutings = document.querySelector("#allOutingsCheck").checked; // Check if 'All Outings' is selected
    const outingCards = document.querySelectorAll('.card');

    outingCards.forEach(card => {
        // Skip 'other' outings if they are supposed to be hidden
        if (card.classList.contains('other-outing') && !showOtherOutings) {
            return; // Don't include 'other' outings in the search if they are hidden
        }

        // Get the card content (text inside the card)
        const cardText = card.textContent.toLowerCase();

        // Check if the card contains the search text
        if (cardText.includes(searchText.toLowerCase())) {
            card.style.display = 'block'; // Show the card if it contains the text
        } else {
            card.style.display = 'none'; // Hide the card if it does not contain the text
        }
    });

    // After filtering, show "No outings for this day" message if no cards are visible
    dayNames.forEach(day => {
        const dayDiv = document.querySelector(`[data-day="${day}"]`);
        if (dayDiv) {
            const visibleCards = dayDiv.querySelectorAll('.card:not([style*="display: none"])');

            const existingNoOutingsMessage = dayDiv.querySelector('.no-outings-message');
            if (visibleCards.length === 0 && !existingNoOutingsMessage) {
                drawNoOutingsMessage(dayDiv);
            } else if (visibleCards.length > 0 && existingNoOutingsMessage) {
                existingNoOutingsMessage.remove();
            }
        }
    });
}

// Add event listener for input field
document.getElementById('outingSearchInput').addEventListener('input', function() {
    const searchText = this.value;
    filterOutings(searchText);
});
