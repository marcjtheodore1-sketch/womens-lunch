/**
 * Women's Lunch Group - Admin Panel JavaScript
 */

// Tab navigation
function showTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`tab-${tabName}`).classList.add('active');
    
    // Load data for the tab
    if (tabName === 'dates') loadDates();
    if (tabName === 'bookings') loadBookings();
    if (tabName === 'archive') loadArchivedBookings();
    if (tabName === 'messages') loadMessageTemplate();
}

// ============================================
// DATES MANAGEMENT
// ============================================

async function loadDates() {
    const container = document.getElementById('admin-dates-list');
    container.innerHTML = '<p class="loading">Loading dates...</p>';
    
    try {
        const response = await fetch('/api/admin/dates');
        const dates = await response.json();
        renderDates(dates);
    } catch (error) {
        container.innerHTML = '<p class="error-text">Failed to load dates</p>';
    }
}

function renderDates(dates) {
    const container = document.getElementById('admin-dates-list');
    
    if (dates.length === 0) {
        container.innerHTML = '<p>No dates configured</p>';
        return;
    }
    
    container.innerHTML = dates.map(date => {
        const isFull = date.spots_left <= 0;
        const statusClass = isFull ? 'full' : '';
        
        return `
            <div class="date-item">
                <div class="date-item-info">
                    <h4>${escapeHtml(date.display)}</h4>
                    <p class="date-item-stats ${statusClass}">
                        ${date.bookings_count} / ${date.max_attendees} booked 
                        ${date.is_bookable ? '(Bookings OPEN)' : '(Bookings CLOSED)'}
                    </p>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" ${date.is_bookable ? 'checked' : ''} 
                           onchange="toggleDateBooking(${date.id}, this.checked)">
                    <span>Open for booking</span>
                </label>
            </div>
        `;
    }).join('');
}

async function toggleDateBooking(dateId, isBookable) {
    try {
        const response = await fetch(`/api/admin/dates/${dateId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_bookable: isBookable })
        });
        
        if (!response.ok) {
            alert('Failed to update date');
            loadDates(); // Reload to reset
        }
    } catch (error) {
        alert('Network error');
        loadDates(); // Reload to reset
    }
}

// ============================================
// BOOKINGS
// ============================================

async function loadBookings() {
    const container = document.getElementById('bookings-by-date');
    container.innerHTML = '<p class="loading">Loading bookings...</p>';
    
    try {
        const response = await fetch('/api/admin/bookings');
        const bookings = await response.json();
        renderBookingsByDate(bookings, 'bookings-by-date', false);
    } catch (error) {
        container.innerHTML = '<p class="error-text">Failed to load bookings</p>';
    }
}

async function loadArchivedBookings() {
    const container = document.getElementById('archive-bookings');
    container.innerHTML = '<p class="loading">Loading archived bookings...</p>';
    
    try {
        const response = await fetch('/api/admin/bookings/archive');
        const bookings = await response.json();
        renderBookingsByDate(bookings, 'archive-bookings', true);
    } catch (error) {
        container.innerHTML = '<p class="error-text">Failed to load archived bookings</p>';
    }
}

function renderBookingsByDate(bookings, containerId, isArchive) {
    const container = document.getElementById(containerId);
    
    if (bookings.length === 0) {
        container.innerHTML = `<p class="no-bookings">${isArchive ? 'No archived bookings' : 'No upcoming bookings'}</p>`;
        return;
    }
    
    // Group by date
    const byDate = {};
    bookings.forEach(booking => {
        if (!byDate[booking.date]) {
            byDate[booking.date] = {
                display: booking.date_display,
                bookings: []
            };
        }
        byDate[booking.date].bookings.push(booking);
    });
    
    // Sort dates
    const sortedDates = Object.keys(byDate).sort();
    if (isArchive) {
        sortedDates.reverse(); // Most recent first for archive
    }
    
    container.innerHTML = sortedDates.map((date, index) => {
        const dateData = byDate[date];
        const isExpanded = index === 0 ? 'expanded' : '';
        
        return `
            <div class="date-booking-group ${isExpanded} ${isArchive ? 'archive' : ''}">
                <div class="date-header" onclick="toggleDateGroup(this)">
                    <span class="toggle-icon">${isExpanded ? '▼' : '▶'}</span>
                    <h4>${escapeHtml(dateData.display)}</h4>
                    <span class="booking-count">(${dateData.bookings.length} booking${dateData.bookings.length !== 1 ? 's' : ''})</span>
                </div>
                <div class="date-bookings">
                    ${dateData.bookings.map(booking => `
                        <div class="booking-row">
                            <div class="booking-info">
                                ${escapeHtml(booking.first_name)} ${escapeHtml(booking.last_name)}
                            </div>
                            <div class="booking-order">
                                ${booking.main_course && booking.drink && booking.main_course !== 'To be decided at the pub' 
                                    ? escapeHtml(booking.main_course) + ' + ' + escapeHtml(booking.drink)
                                    : '<em>Order to be decided at the pub</em>'}
                                ${booking.dietary_requirements ? `<small>🥗 ${escapeHtml(booking.dietary_requirements)}</small>` : ''}
                            </div>
                            <div class="booking-user">
                                ${escapeHtml(booking.email)}
                                ${booking.phone ? `<small>📞 ${escapeHtml(booking.phone)}</small>` : ''}
                                ${booking.is_first_time ? '<small>⭐ First time attending</small>' : ''}
                            </div>
                            <div class="booking-actions">
                                <button class="btn btn-small btn-danger" onclick="deleteBooking(${booking.id}, '${containerId}')">Delete</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');
}

function toggleDateGroup(header) {
    const group = header.parentElement;
    const isExpanded = group.classList.contains('expanded');
    
    if (isExpanded) {
        group.classList.remove('expanded');
        header.querySelector('.toggle-icon').textContent = '▶';
    } else {
        group.classList.add('expanded');
        header.querySelector('.toggle-icon').textContent = '▼';
    }
}

async function deleteBooking(bookingId, containerId) {
    if (!confirm('Are you sure you want to permanently delete this booking? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/admin/bookings/${bookingId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Reload the bookings list
            if (containerId === 'bookings-by-date') {
                loadBookings();
            } else {
                loadArchivedBookings();
            }
        } else {
            alert('Failed to delete booking');
        }
    } catch (error) {
        alert('Network error');
    }
}

// ============================================
// MESSAGE TEMPLATE
// ============================================

const DEFAULT_TEMPLATE = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Tahoma, Verdana, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1a1a1a; max-width: 600px; margin: 0 auto; padding: 20px; }
        h2 { color: #276749; font-size: 18px; margin-bottom: 5px; }
        .header { background: #f0fff4; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #68d391; }
        .section { margin-bottom: 15px; }
        .label { font-weight: bold; color: #276749; }
        .order-box { background: #f7fafc; padding: 12px; border-radius: 6px; margin: 10px 0; }
        a { color: #276749; text-decoration: underline; }
        .cancel-link { background: #f0fff4; padding: 12px; border-radius: 6px; text-align: center; margin: 15px 0; }
        .footer { margin-top: 25px; padding-top: 15px; border-top: 1px solid #c6f6d5; font-size: 12px; color: #4a4a4a; }
    </style>
</head>
<body>
    <div class="header">
        <h2>✅ Booking Confirmed!</h2>
        <p>Dear {{name}}, your booking for the LAGC Autistic Women's Lunch has been confirmed.</p>
    </div>

    <div class="section">
        <span class="label">Date:</span> {{date}}<br>
        <span class="label">Time:</span> 12:00 PM - 1:00 PM<br>
        <span class="label">Venue:</span> Cittie of Yorke, 22 High Holborn, London WC1V 6BN<br>
        <span class="label">Location:</span> <a href="https://maps.app.goo.gl/Wyh2E9CQU7UqpBCs9">View on Google Maps</a>
    </div>

    <div class="section">
        <span class="label">Meeting Options:</span>
        <ul>
            <li>Meet a volunteer at Holy Sepulchre Church at 11:40 AM (they will walk with you to the pub)</li>
            <li>Or meet directly at the pub at 12:00 PM</li>
        </ul>
    </div>

    <div class="order-box">
        <span class="label">Your Order:</span><br>
        Main: {{main_course}}<br>
        Drink: {{drink}}
        {{dietary_requirements}}
    </div>

    <div class="section">
        <span class="label">What to expect:</span><br>
        This is a relaxed, neuroaffirming space for autistic women to connect over lunch. You can choose a main course and one non-alcoholic drink which London Autism Group Charity will be happy to cover. There is always at least one charity volunteer onsite to welcome you and help you feel comfortable.
    </div>

    <div class="section">
        Self-identification is fine — you don't need a formal diagnosis.
    </div>

    <div class="cancel-link">
        <span class="label">Need to cancel?</span><br>
        <a href="{{cancel_url}}">Click here to cancel your booking</a>
    </div>

    <div class="footer">
        We look forward to seeing you!<br><br>
        Best regards,<br>
        <strong>LAGC Women's Lunch Team</strong><br>
        London Autism Group Charity
    </div>
</body>
</html>`;

async function loadMessageTemplate() {
    const textarea = document.getElementById('confirmation-template');
    
    try {
        const response = await fetch('/api/admin/settings');
        const settings = await response.json();
        textarea.value = settings.confirmation_message || DEFAULT_TEMPLATE;
    } catch (error) {
        textarea.value = DEFAULT_TEMPLATE;
    }
}

async function saveMessageTemplate() {
    const template = document.getElementById('confirmation-template').value;
    
    try {
        const response = await fetch('/api/admin/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmation_message: template })
        });
        
        if (response.ok) {
            alert('Template saved successfully');
        } else {
            alert('Failed to save template');
        }
    } catch (error) {
        alert('Network error');
    }
}

function resetMessageTemplate() {
    if (confirm('Reset to default template?')) {
        document.getElementById('confirmation-template').value = DEFAULT_TEMPLATE;
    }
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

// Load dates on page load
document.addEventListener('DOMContentLoaded', () => {
    loadDates();
});
