/**
 * Women's Lunch Group - Main Application JavaScript
 */

// State
let state = {
    dates: [],
    selectedDate: null,
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    mainCourse: '',
    drink: '',
    dietary: '',
    meetingPreference: 'church',
    isFirstTime: true,
    additionalInfo: ''
};

// DOM Elements - initialized after DOM is ready
let elements = {};

function initElements() {
    elements = {
        firstNameInput: document.getElementById('first-name'),
        lastNameInput: document.getElementById('last-name'),
        emailInput: document.getElementById('email'),
        phoneInput: document.getElementById('phone'),
        dietaryInput: document.getElementById('dietary'),
        additionalInfoInput: document.getElementById('additional-info'),
        bookingSummary: document.getElementById('booking-summary'),
        confirmationMessage: document.getElementById('confirmation-message'),
        myBookingsList: document.getElementById('my-bookings-list')
    };
}

// Steps
const steps = {
    date: document.getElementById('step-date'),
    details: document.getElementById('step-details'),
    final: document.getElementById('step-final'),
    confirmation: document.getElementById('step-confirmation')
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initElements();
    loadDates();
});

// ============================================
// DATA LOADING
// ============================================

async function loadDates() {
    const container = document.getElementById('dates-info');
    const selectionContainer = document.getElementById('date-selection');
    
    try {
        const response = await fetch('/api/dates');
        state.dates = await response.json();
        
        // Show info about booking system
        const bookableDates = state.dates.filter(d => d.is_bookable);
        if (bookableDates.length === 0) {
            container.innerHTML = '<p class="notice">Bookings are currently closed. Check back soon for the next lunch date!</p>';
            selectionContainer.innerHTML = '';
            return;
        }
        
        // Show all dates with status
        container.innerHTML = '<p>Bookings are open for the next lunch. Future dates are shown for reference.</p>';
        
        selectionContainer.innerHTML = state.dates.map(date => {
            const isBookable = date.is_bookable && !date.is_full;
            const statusClass = date.is_full ? 'full' : (date.is_bookable ? 'available' : '');
            const statusText = date.is_full ? 'Fully Booked' : (date.is_bookable ? `${date.spots_left} spots left` : 'Opening soon');
            
            return `
                <div class="date-card ${isBookable ? '' : 'disabled'}" 
                     ${isBookable ? `onclick="selectDate(${date.id})"` : ''}>
                    <div class="date-info">
                        <span class="date-main">${escapeHtml(date.display)}</span>
                        <span class="date-status ${statusClass}">${escapeHtml(statusText)}</span>
                    </div>
                    ${isBookable ? '<span class="select-hint">Click to select →</span>' : ''}
                </div>
            `;
        }).join('');
        
    } catch (error) {
        container.innerHTML = '<p class="error-text">Failed to load dates. Please refresh the page.</p>';
    }
}

// ============================================
// STEP NAVIGATION
// ============================================

function selectDate(dateId) {
    state.selectedDate = state.dates.find(d => d.id === dateId);
    
    if (!state.selectedDate || !state.selectedDate.is_bookable) {
        return;
    }
    
    showStep('details');
}

function showStep(stepName) {
    Object.keys(steps).forEach(key => {
        if (key === stepName) {
            steps[key].classList.remove('hidden');
        } else {
            steps[key].classList.add('hidden');
        }
    });
}

function resetDate() {
    state.selectedDate = null;
    showStep('date');
}

function showDetailsStep() {
    showStep('details');
}

function showFinalStep() {
    // Validate details
    const firstName = elements.firstNameInput.value.trim();
    const lastName = elements.lastNameInput.value.trim();
    const email = elements.emailInput.value.trim();
    
    if (!firstName) {
        alert('Please enter your first name');
        return;
    }
    if (!lastName) {
        alert('Please enter your last name');
        return;
    }
    if (!email || !email.includes('@')) {
        alert('Please enter a valid email address');
        return;
    }
    
    // Get meeting preference
    const meetingRadios = document.getElementsByName('meeting-preference');
    for (const radio of meetingRadios) {
        if (radio.checked) {
            state.meetingPreference = radio.value;
            break;
        }
    }
    
    // Save to state
    state.firstName = firstName;
    state.lastName = lastName;
    state.email = email;
    state.phone = elements.phoneInput.value.trim();
    state.dietary = elements.dietaryInput.value.trim();
    
    showStep('final');
    updateBookingSummary();
}



function updateBookingSummary() {
    const dateDisplay = state.selectedDate ? state.selectedDate.display : '';
    
    elements.bookingSummary.innerHTML = `
        <h3>Booking Summary</h3>
        <div class="summary-row">
            <span>Name:</span>
            <strong>${escapeHtml(state.firstName)} ${escapeHtml(state.lastName)}</strong>
        </div>
        <div class="summary-row">
            <span>Email:</span>
            <span>${escapeHtml(state.email)}</span>
        </div>
        <div class="summary-row">
            <span>Date:</span>
            <span>${escapeHtml(dateDisplay)}</span>
        </div>
        ${state.dietary ? `
        <div class="summary-row">
            <span>Dietary Requirements:</span>
            <span>${escapeHtml(state.dietary)}</span>
        </div>
        ` : ''}
    `;
}

function showDetailsStepFromFinal() {
    showStep('details');
}



// ============================================
// BOOKING SUBMISSION
// ============================================

async function submitBooking() {
    // Get first time status
    const firstTimeRadios = document.getElementsByName('first-time');
    for (const radio of firstTimeRadios) {
        if (radio.checked) {
            state.isFirstTime = radio.value === 'true';
            break;
        }
    }
    
    state.additionalInfo = elements.additionalInfoInput.value.trim();
    
    const bookingData = {
        lunch_date_id: state.selectedDate.id,
        first_name: state.firstName,
        last_name: state.lastName,
        email: state.email,
        phone: state.phone,
        main_course: '',
        drink: '',
        dietary_requirements: state.dietary,
        meeting_preference: state.meetingPreference,
        is_first_time: state.isFirstTime,
        additional_info: state.additionalInfo
    };
    
    try {
        const response = await fetch('/api/book', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bookingData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            elements.confirmationMessage.innerHTML = result.confirmation_message;
            showStep('confirmation');
        } else {
            alert(result.error || 'Failed to create booking');
        }
    } catch (error) {
        alert('Network error. Please try again.');
    }
}

function resetBooking() {
    state.selectedDate = null;
    state.firstName = '';
    state.lastName = '';
    state.email = '';
    state.phone = '';
    state.mainCourse = '';
    state.drink = '';
    state.dietary = '';
    state.meetingPreference = 'church';
    state.isFirstTime = true;
    state.additionalInfo = '';
    
    elements.firstNameInput.value = '';
    elements.lastNameInput.value = '';
    elements.emailInput.value = '';
    elements.phoneInput.value = '';
    elements.dietaryInput.value = '';
    elements.additionalInfoInput.value = '';
    
    // Reset radio buttons
    const firstTimeRadios = document.getElementsByName('first-time');
    for (const radio of firstTimeRadios) {
        if (radio.value === 'true') {
            radio.checked = true;
        }
    }
    
    showStep('date');
    loadDates();
}

// ============================================
// MY BOOKINGS
// ============================================

async function loadMyBookings() {
    const emailInput = document.getElementById('my-bookings-email');
    const email = emailInput ? emailInput.value.trim() : '';
    
    if (!email) {
        alert('Please enter your email address');
        return;
    }
    
    const listElement = document.getElementById('my-bookings-list');
    if (!listElement) {
        console.error('my-bookings-list element not found');
        return;
    }
    
    // Show loading
    listElement.innerHTML = '<p>Loading...</p>';
    
    try {
        console.log('Fetching bookings for:', email);
        const response = await fetch('/api/my-bookings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email })
        });
        
        console.log('Response status:', response.status);
        const bookings = await response.json();
        console.log('Bookings:', bookings);
        
        if (response.ok) {
            renderMyBookings(bookings);
        } else {
            listElement.innerHTML = `<p class="error-text">${bookings.error || 'Failed to load bookings'}</p>`;
        }
    } catch (error) {
        console.error('Error loading bookings:', error);
        listElement.innerHTML = '<p class="error-text">Failed to load bookings. Check console for details.</p>';
    }
}

function renderMyBookings(bookings) {
    if (!elements.myBookingsList) {
        console.error('myBookingsList element not found');
        return;
    }
    
    if (bookings.length === 0) {
        elements.myBookingsList.innerHTML = '<p>No upcoming bookings found</p>';
        return;
    }
    
    elements.myBookingsList.innerHTML = bookings.map(booking => `
        <div class="booking-item">
            <div class="booking-item-info">
                <h4>${escapeHtml(booking.date_display)}</h4>
                <p>${booking.main_course ? escapeHtml(booking.main_course) + ' + ' + escapeHtml(booking.drink) : 'Order to be decided at the pub'}</p>
            </div>
            <a href="/cancel/${booking.cancel_token}" class="btn btn-small btn-danger">Cancel</a>
        </div>
    `).join('');
}

// ============================================
// UTILITIES
// ============================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
