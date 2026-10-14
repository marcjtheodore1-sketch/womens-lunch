/* Private Women's Lunch register. Every save is acknowledged by the server. */
let lunchRegister = null;
let lunchHistory = null;
let registerRequest = 0;
let registerSaving = false;
let registerLoading = false;
const attendanceLabels = {unrecorded: 'Not recorded', attended: 'Attended', no_show: 'Did not attend', cancelled: 'Cancelled', late_cancelled: 'Late cancellation'};
const attendanceElement = id => document.getElementById(id);

async function attendanceFetch(url, options) {
    const response = await fetch(url, options);
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Your admin session may have expired. Refresh the page and sign in again.');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not save. Refresh the register and try again.');
    return data;
}

function attendanceMessage(message, error = false) {
    const element = attendanceElement('attendance-message');
    element.textContent = message;
    element.className = error ? 'attendance-message error-text' : 'attendance-message';
}

function londonSavedTime(value) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', day: 'numeric', month: 'long', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true}).formatToParts(new Date(value)).map(part => [part.type, part.value]));
    const day = Number(parts.day);
    const suffix = day % 100 >= 11 && day % 100 <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[day % 10] || 'th');
    return `${day}${suffix} ${parts.month} ${parts.year}, ${parts.hour}${parts.minute === '00' ? '' : '.' + parts.minute}${parts.dayPeriod.toLowerCase()}`;
}

function hasUnsavedAttendanceNotes() {
    return [...document.querySelectorAll('[data-note]')].some(input => input.value !== lunchRegister?.records.find(record => record.id === Number(input.dataset.note))?.note);
}

async function loadAttendanceDates() {
    try {
        const dates = await attendanceFetch('/api/admin/lunch-attendance/dates');
        const selector = attendanceElement('attendance-date');
        selector.innerHTML = dates.map(item => `<option value="${item.id}">${escapeHtml(item.display)} (${item.bookings} booking${item.bookings === 1 ? '' : 's'})</option>`).join('');
        if (!dates.length) {
            attendanceElement('attendance-register').textContent = 'No lunch dates have been added yet.';
            return;
        }
        const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
        const preferred = dates.find(item => item.date === today) || dates.find(item => item.can_record && item.bookings) || dates.filter(item => !item.can_record).at(-1) || dates[0];
        selector.value = preferred.id;
        await loadAttendanceRegister();
    } catch (error) {
        attendanceElement('attendance-register').textContent = 'The register could not be loaded.';
        attendanceMessage(error.message, true);
    }
}

async function loadAttendanceRegister() {
    if (registerSaving) return;
    const selector = attendanceElement('attendance-date');
    if (hasUnsavedAttendanceNotes() && !confirm('There are notes you have not saved. Discard those edits and load the register?')) {
        selector.value = lunchRegister.id;
        return;
    }
    const generation = ++registerRequest;
    registerLoading = true;
    attendanceElement('attendance-register').inert = true;
    attendanceElement('attendance-register').setAttribute('aria-busy', 'true');
    attendanceMessage('Loading register...');
    try {
        const data = await attendanceFetch(`/api/admin/lunch-attendance/${selector.value}`);
        if (generation !== registerRequest) return;
        lunchRegister = data;
        attendanceElement('attendance-register').innerHTML = data.records.map(attendanceCard).join('') || '<p>No bookings for this lunch.</p>';
        const link = attendanceElement('attendance-export');
        link.href = `/api/admin/lunch-attendance/${data.id}/export`;
        link.hidden = false;
        updateAttendanceCounts();
        filterAttendanceRegister();
        attendanceMessage(data.can_record ? 'Register loaded. Choices save immediately. Notes save when you choose an option or tap Save note.' : 'You can record attendance from 12pm on this lunch date. Tap Refresh register then.');
    } catch (error) {
        if (generation !== registerRequest) return;
        if (lunchRegister) selector.value = lunchRegister.id;
        attendanceMessage(error.message, true);
    } finally {
        if (generation === registerRequest) {
            registerLoading = false;
            attendanceElement('attendance-register').inert = false;
            attendanceElement('attendance-register').removeAttribute('aria-busy');
        }
    }
}

function attendanceCard(record) {
    const disabled = !lunchRegister?.can_record ? 'disabled' : '';
    const buttons = Object.entries(attendanceLabels).filter(([status]) => status !== 'unrecorded').map(([status, label]) => {
        const blocked = disabled || (status === 'no_show' && (!lunchRegister.can_record_absence || record.cancelled_at)) ? 'disabled' : '';
        return `<button type="button" class="attendance-choice ${status}" data-save="${status}" aria-pressed="${record.status === status}" ${blocked}>${label}</button>`;
    }).join('');
    return `<article class="attendance-card" data-booking="${record.id}">
        <div class="attendance-card-heading"><div><h3>${escapeHtml(record.name)}</h3><p>${escapeHtml(record.email)}</p></div><span class="attendance-badge ${record.status}">${escapeHtml(record.status_label)}</span></div>
        ${record.automatic_cancellation ? `<p class="attendance-auto">From the online cancellation, ${escapeHtml(londonSavedTime(record.cancelled_at))} (London time).</p>` : ''}
        <div class="attendance-choices" role="group" aria-label="Attendance for ${escapeHtml(record.name)}">${buttons}</div>
        ${lunchRegister.can_record && !lunchRegister.can_record_absence ? '<p class="hint">“Did not attend” is available after lunch finishes at 1pm. Tap Refresh register then.</p>' : ''}
        <div class="attendance-card-footer"><button type="button" class="attendance-clear" data-save="clear" ${disabled || !record.manual_status ? 'disabled' : ''}>Clear manual choice</button><span>${record.updated_at ? `Saved ${escapeHtml(londonSavedTime(record.updated_at))}` : 'No manual record yet'}</span></div>
        <details class="attendance-details"><summary>Note and changes${record.note ? ' · note saved' : ''}</summary>
            <label for="attendance-note-${record.id}">Optional factual note</label><p class="hint">For example, “Called at 10am to cancel”. Keep it brief and avoid sensitive personal details.</p>
            <textarea id="attendance-note-${record.id}" data-note="${record.id}" maxlength="1000" rows="2" ${disabled}>${escapeHtml(record.note)}</textarea>
            <button type="button" class="btn btn-secondary btn-small" data-save="note" ${disabled}>Save note</button>
            <button type="button" class="attendance-clear" data-changes="${record.id}">View saved changes</button><div class="attendance-changes"></div>
        </details>
        <p class="attendance-card-status" role="status" aria-live="polite"></p>
    </article>`;
}

function updateAttendanceCounts() {
    const counts = Object.fromEntries(Object.keys(attendanceLabels).map(status => [status, lunchRegister.records.filter(record => record.status === status).length]));
    attendanceElement('attendance-counts').innerHTML = Object.entries(attendanceLabels).map(([status, label]) => `<div class="attendance-count ${status}"><strong>${counts[status]}</strong><span>${status === 'unrecorded' ? 'Still to check' : label}</span></div>`).join('');
}

function filterAttendanceRegister() {
    const search = attendanceElement('attendance-search').value.trim().toLocaleLowerCase('en-GB');
    const pending = attendanceElement('attendance-unrecorded').checked;
    document.querySelectorAll('[data-booking]').forEach(card => {
        const record = lunchRegister.records.find(item => item.id === Number(card.dataset.booking));
        card.hidden = !`${record.name} ${record.email}`.toLocaleLowerCase('en-GB').includes(search) || (pending && record.status !== 'unrecorded');
    });
    let empty = attendanceElement('attendance-no-matches');
    if (!empty) {
        empty = document.createElement('p');
        empty.id = 'attendance-no-matches';
        empty.textContent = 'No bookings match this filter.';
        attendanceElement('attendance-register').append(empty);
    }
    empty.hidden = !lunchRegister?.records.length || [...document.querySelectorAll('[data-booking]')].some(card => !card.hidden);
}

async function saveAttendance(button, card) {
    if (registerSaving || registerLoading) return;
    const record = lunchRegister.records.find(item => item.id === Number(card.dataset.booking));
    const status = button.dataset.save === 'note' ? record.manual_status : button.dataset.save === 'clear' ? null : button.dataset.save;
    registerSaving = true;
    attendanceElement('attendance-date').disabled = true;
    attendanceElement('attendance-refresh').disabled = true;
    card.setAttribute('aria-busy', 'true');
    card.querySelector('.attendance-card-status').textContent = 'Saving...';
    try {
        const saved = await attendanceFetch(`/api/admin/lunch-attendance/booking/${record.id}`, {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': adminCsrfToken},
            body: JSON.stringify({status, note: card.querySelector('textarea').value, version: record.version}),
        });
        const expanded = card.querySelector('details').open;
        lunchRegister.records[lunchRegister.records.indexOf(record)] = saved;
        card.outerHTML = attendanceCard(saved);
        const replacement = document.querySelector(`[data-booking="${record.id}"]`);
        replacement.querySelector('details').open = expanded;
        replacement.querySelector('.attendance-card-status').textContent = 'Saved';
        replacement.querySelector(`[data-save="${button.dataset.save}"]`)?.focus();
        updateAttendanceCounts();
        filterAttendanceRegister();
        attendanceMessage(`${saved.name}: ${saved.status_label}. Saved.`);
        lunchHistory = null;
        if (attendanceElement('attendance-history').open) await loadAttendanceHistory();
    } catch (error) {
        card.querySelector('.attendance-card-status').textContent = `Not saved. ${error.message}`;
        attendanceMessage(`Not saved. ${error.message}`, true);
    } finally {
        registerSaving = false;
        attendanceElement('attendance-date').disabled = false;
        attendanceElement('attendance-refresh').disabled = false;
        card.removeAttribute('aria-busy');
    }
}

async function loadAttendanceHistory() {
    const container = attendanceElement('attendance-people');
    container.textContent = 'Loading history...';
    try {
        lunchHistory = await attendanceFetch('/api/admin/lunch-attendance/history');
        attendanceElement('attendance-history-period').textContent = `Lunches since ${lunchHistory.since}, grouped by booking email address. Shared email addresses may represent more than one person.`;
        renderAttendanceHistory();
    } catch (error) { container.textContent = error.message; }
}

function renderAttendanceHistory() {
    if (!lunchHistory) return;
    const search = attendanceElement('attendance-history-search').value.trim().toLocaleLowerCase('en-GB');
    const filter = attendanceElement('attendance-history-filter').value;
    const people = lunchHistory.people.filter(person => `${person.name} ${person.email}`.toLocaleLowerCase('en-GB').includes(search) && (filter === 'all' || person.counts[filter] > 0));
    attendanceElement('attendance-people').innerHTML = people.map(person => `<details class="attendance-person"><summary><span><strong>${escapeHtml(person.name)}</strong><small>${escapeHtml(person.email)}</small></span><span class="attendance-person-counts">${person.counts.attended} attended · ${person.counts.no_show} missed · ${person.counts.late_cancelled} late cancellations<small>${person.counts.cancelled} cancelled · ${person.counts.unrecorded} not recorded</small></span></summary><ul>${person.records.map(record => `<li><strong>${escapeHtml(record.date_display)}</strong><span class="attendance-badge ${record.status}">${record.status_label}</span>${record.note ? `<p>${escapeHtml(record.note)}</p>` : ''}<button type="button" class="attendance-clear" data-open-register="${record.date}">Open this register</button></li>`).join('')}</ul></details>`).join('') || '<p>No people match this view.</p>';
}

document.addEventListener('DOMContentLoaded', () => {
    loadAttendanceDates();
    attendanceElement('attendance-date').addEventListener('change', loadAttendanceRegister);
    attendanceElement('attendance-refresh').addEventListener('click', loadAttendanceRegister);
    attendanceElement('attendance-search').addEventListener('input', filterAttendanceRegister);
    attendanceElement('attendance-unrecorded').addEventListener('change', filterAttendanceRegister);
    attendanceElement('attendance-history-search').addEventListener('input', renderAttendanceHistory);
    attendanceElement('attendance-history-filter').addEventListener('change', renderAttendanceHistory);
    attendanceElement('attendance-history').addEventListener('toggle', event => { if (event.target.open && !lunchHistory) loadAttendanceHistory(); });
    attendanceElement('attendance-register').addEventListener('click', async event => {
        const button = event.target.closest('button');
        if (!button) return;
        const card = button.closest('[data-booking]');
        if (button.dataset.save) return saveAttendance(button, card);
        if (button.dataset.changes) {
            const container = card.querySelector('.attendance-changes');
            try {
                const changes = await attendanceFetch(`/api/admin/lunch-attendance/booking/${button.dataset.changes}/changes`);
                container.innerHTML = changes.map(change => `<p><strong>${escapeHtml(change.status_label)}</strong> · ${escapeHtml(londonSavedTime(change.recorded_at))}${change.note ? `<br>${escapeHtml(change.note)}` : ''}</p>`).join('') || '<p>No manual changes recorded.</p>';
            } catch (error) { container.textContent = error.message; }
        }
    });
    attendanceElement('attendance-people').addEventListener('click', event => {
        const button = event.target.closest('[data-open-register]');
        if (!button || registerSaving) return;
        const selector = attendanceElement('attendance-date');
        attendanceFetch('/api/admin/lunch-attendance/dates').then(dates => {
            const lunch = dates.find(item => item.date === button.dataset.openRegister);
            if (lunch) { selector.value = lunch.id; loadAttendanceRegister(); attendanceElement('attendance-date').scrollIntoView({behavior: 'smooth', block: 'center'}); }
        }).catch(error => attendanceMessage(error.message, true));
    });
    window.addEventListener('beforeunload', event => { if (registerSaving || hasUnsavedAttendanceNotes()) { event.preventDefault(); event.returnValue = ''; } });
});
