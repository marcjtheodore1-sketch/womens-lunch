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
    isFirstTime: true,
    additionalInfo: ''
};

// DOM Elements
const elements = {
    firstNameInput: document.getElementById('first-name'),
    lastNameInput: document.getElementById('last-name'),
    emailInput: document.getElementById('email'),
    phoneInput: document.getElementById('phone'),
    mainCourseInput: document.getElementById('main-course'),
    drinkInput: document.getElementById('drink'),
    dietaryInput: document.getElementById('dietary'),
    additionalInfoInput: document.getElementById('additional-info'),
    bookingSummary: document.getElementById('booking-summary'),
    confirmationMessage: document.getElementById('confirmation-message'),
    myBookingsList: document.getElementById('my-bookings-list')
};

// Steps
const steps = {
    date: document.getElementById('step-date'),
    details: document.getElementById('step-details'),
    menu: document.getElementById('step-menu'),
    final: document.getElementById('step-final'),
    confirmation: document.getElementById('step-confirmation')
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
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

function showMenuStep() {
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
    
    // Save to state
    state.firstName = firstName;
    state.lastName = lastName;
    state.email = email;
    state.phone = elements.phoneInput.value.trim();
    
    showStep('menu');
}

function showFinalStep() {
    // Validate menu
    const mainCourse = elements.mainCourseInput.value.trim();
    const drink = elements.drinkInput.value.trim();
    
    if (!mainCourse) {
        alert('Please enter your main course selection');
        return;
    }
    if (!drink) {
        alert('Please enter your drink selection');
        return;
    }
    
    // Save to state
    state.mainCourse = mainCourse;
    state.drink = drink;
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
        <div class="summary-row">
            <span>Your Order:</span>
            <span>${escapeHtml(state.mainCourse)} + ${escapeHtml(state.drink)}</span>
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

function showMenuStepFromFinal() {
    showStep('menu');
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
        main_course: state.mainCourse,
        drink: state.drink,
        dietary_requirements: state.dietary,
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
            elements.confirmationMessage.textContent = result.confirmation_message;
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
    state.isFirstTime = true;
    state.additionalInfo = '';
    
    elements.firstNameInput.value = '';
    elements.lastNameInput.value = '';
    elements.emailInput.value = '';
    elements.phoneInput.value = '';
    elements.mainCourseInput.value = '';
    elements.drinkInput.value = '';
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
    const email = document.getElementById('my-bookings-email').value.trim();
    
    if (!email) {
        alert('Please enter your email address');
        return;
    }
    
    try {
        const response = await fetch('/api/my-bookings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        const bookings = await response.json();
        
        if (response.ok) {
            renderMyBookings(bookings);
        } else {
            elements.myBookingsList.innerHTML = `<p class="error-text">${bookings.error}</p>`;
        }
    } catch (error) {
        elements.myBookingsList.innerHTML = '<p class="error-text">Failed to load bookings</p>';
    }
}

function renderMyBookings(bookings) {
    if (bookings.length === 0) {
        elements.myBookingsList.innerHTML = '<p>No upcoming bookings found</p>';
        return;
    }
    
    elements.myBookingsList.innerHTML = bookings.map(booking => `
        <div class="booking-item">
            <div class="booking-item-info">
                <h4>${escapeHtml(booking.date_display)}</h4>
                <p>${escapeHtml(booking.main_course)} + ${escapeHtml(booking.drink)}</p>
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
