/**
 * ===================================================================
 *  Travel Management Dashboard — API-Driven
 * ===================================================================
 *
 *  DATA FLOW:
 *    1. Page loads → fetch('/api/my-trips')
 *    2. If 401 → redirect to /login
 *    3. API returns { draft_trips: [...], final_trips: [...] }
 *    4. JS renders cards dynamically into both columns
 *    5. "Create New Draft" → redirects to /trip (trip creation form)
 * ===================================================================
 */

// ──────────────────────────────────────────────
//  STATE
// ──────────────────────────────────────────────
let allDraftTrips = [];
let allFinalTrips = [];
let isDeleteModeActive = false;

// ──────────────────────────────────────────────
//  HELPERS
// ──────────────────────────────────────────────

/**
 * Format a datetime string into a friendly relative time.
 */
function timeAgo(dateStr) {
    if (!dateStr) return '';
    const now = new Date();
    const then = new Date(dateStr);
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return then.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/**
 * Get a Font-Awesome icon class based on pace/type.
 */
function getPaceIcon(pace) {
    const map = {
        'relaxed': 'fa-umbrella-beach',
        'balanced': 'fa-route',
        'packed': 'fa-bolt'
    };
    return map[pace] || 'fa-suitcase-rolling';
}

// ──────────────────────────────────────────────
//  CARD COMPONENTS
// ──────────────────────────────────────────────

function createDraftCard(trip) {
    const icon = getPaceIcon(trip.pace);
    const ago = timeAgo(trip.created_at);
    const regions = [trip.start_region, trip.end_region].filter(Boolean).join(' → ');
    const days = trip.trip_days ? `${trip.trip_days} days` : '';
    const meta = [regions, days].filter(Boolean).join(' · ');

    return `
    <div class="draft-card" data-trip-id="${trip.trip_id}" id="draft-card-${trip.trip_id}">
        <div class="card-icon draft-icon">
            <i class="fa-solid ${icon}"></i>
        </div>
        <div class="card-content">
            <div class="card-title">${trip.trip_name}</div>
            <div class="card-meta">
                <i class="fa-regular fa-clock"></i>
                ${ago}${meta ? ' · ' + meta : ''}
            </div>
        </div>
        <div class="card-action">
            <button class="btn-select" onclick="selectDraft(${trip.trip_id})" id="btn-select-${trip.trip_id}">
                Open
            </button>
        </div>
    </div>`;
}

function createFinalCard(trip) {
    const icon = getPaceIcon(trip.pace);
    const regions = [trip.start_region, trip.end_region].filter(Boolean).join(' → ');
    const days = trip.trip_days ? `${trip.trip_days} days` : '';
    const meta = [regions, days].filter(Boolean).join(' · ');

    return `
    <a class="final-card" href="/itinerary/${trip.trip_id}" data-trip-id="${trip.trip_id}" id="final-card-${trip.trip_id}">
        <div class="card-icon final-icon">
            <i class="fa-solid ${icon}"></i>
        </div>
        <div class="card-content">
            <div class="card-title">${trip.trip_name}</div>
            <div class="card-status">
                <i class="fa-solid fa-circle-check"></i>
                Confirmed
            </div>
            ${meta ? `<div class="card-dates">${meta}</div>` : ''}
        </div>
        <div class="card-action">
            <i class="fa-solid fa-chevron-right arrow-icon"></i>
        </div>
    </a>`;
}

// ──────────────────────────────────────────────
//  RENDER FUNCTIONS
// ──────────────────────────────────────────────

function renderDraftTrips(trips) {
    const container = document.getElementById("draft-trips-list");
    if (!container) return;

    if (trips.length === 0) {
        container.innerHTML = `
            <div class="trips-empty-state">
                <i class="fa-solid fa-pencil-ruler"></i>
                <h3>No draft trips yet</h3>
                <p>Click "Create New Draft" below to start planning.</p>
            </div>`;
    } else {
        container.innerHTML = trips.map(createDraftCard).join("");
    }

    // Update badge count
    const badge = document.getElementById("draft-badge");
    if (badge) badge.textContent = `${trips.length} Draft${trips.length !== 1 ? "s" : ""}`;
}

function renderFinalTrips(trips) {
    const container = document.getElementById("final-trips-list");
    if (!container) return;

    if (trips.length === 0) {
        container.innerHTML = `
            <div class="trips-empty-state">
                <i class="fa-solid fa-check-double"></i>
                <h3>No confirmed trips yet</h3>
                <p>Finalize a draft to see it here.</p>
            </div>`;
    } else {
        container.innerHTML = trips.map(createFinalCard).join("");
    }

    // Update badge count
    const badge = document.getElementById("final-badge");
    if (badge) badge.textContent = `${trips.length} Active`;
}

// ──────────────────────────────────────────────
//  API FETCH
// ──────────────────────────────────────────────

async function loadTrips() {
    try {
        let ok;
        let status;
        let data;

        if (typeof window.apiGetJson === 'function') {
            const result = await window.apiGetJson('/api/my-trips');
            ok = result.ok;
            status = result.status;
            data = result.data;
        } else {
            const response = await fetch('/api/my-trips');
            ok = response.ok;
            status = response.status;
            data = await response.json();
        }

        // 401 → redirect to login
        if (status === 401) {
            console.warn('[Dashboard] Not logged in — redirecting to /login');
            window.location.href = '/login?next=/dashboard';
            return;
        }

        if (!ok) {
            throw new Error(`Server error: ${status}`);
        }

        if (data.error) {
            console.error('[Dashboard] API error:', data.error);
            renderDraftTrips([]);
            renderFinalTrips([]);
            return;
        }

        allDraftTrips = data.draft_trips || [];
        allFinalTrips = data.final_trips || [];

        console.log(`[Dashboard] Loaded ${allDraftTrips.length} drafts, ${allFinalTrips.length} final trips`);

        renderDraftTrips(allDraftTrips);
        renderFinalTrips(allFinalTrips);

    } catch (err) {
        console.error('[Dashboard] Failed to load trips:', err);
        renderDraftTrips([]);
        renderFinalTrips([]);
    }
}

// ──────────────────────────────────────────────
//  EVENT HANDLERS
// ──────────────────────────────────────────────

function selectDraft(tripId) {
    // Navigate to the draft trip editor
    window.location.href = `/draft_trip/${tripId}`;
}

function createNewDraft() {
    // Navigate to the trip creation form
    window.location.href = '/trip';
}

/**
 * Enter delete mode: show checkboxes and action buttons
 */
function enterDeleteMode() {
    isDeleteModeActive = true;

    // Show checkboxes and action bar
    document.querySelectorAll('.checkbox-wrapper').forEach(wrapper => {
        wrapper.classList.add('visible');
        wrapper.style.display = 'flex';
    });

    document.querySelectorAll('.draft-card').forEach(card => {
        card.classList.add('delete-mode-active');
    });

    const actionBar = document.getElementById('delete-mode-actions');
    if (actionBar) {
        actionBar.classList.add('visible');
        actionBar.style.display = 'flex';
    }

    const deleteBtn = document.getElementById('btn-delete-drafts');
    if (deleteBtn) {
        deleteBtn.style.display = 'none';
    }

    // Attach checkbox event listeners
    document.querySelectorAll('.trip-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', handleCheckboxChange);
    });

    console.log('[Dashboard] Entered delete mode');
}

/**
 * Exit delete mode: hide checkboxes and action buttons, uncheck all
 */
function exitDeleteMode() {
    isDeleteModeActive = false;

    // Hide checkboxes and action bar
    document.querySelectorAll('.checkbox-wrapper').forEach(wrapper => {
        wrapper.classList.remove('visible');
        wrapper.style.display = 'none';
    });

    document.querySelectorAll('.draft-card').forEach(card => {
        card.classList.remove('delete-mode-active');
    });

    document.querySelectorAll('.trip-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });

    const actionBar = document.getElementById('delete-mode-actions');
    if (actionBar) {
        actionBar.classList.remove('visible');
        actionBar.style.display = 'none';
    }

    const deleteBtn = document.getElementById('btn-delete-drafts');
    if (deleteBtn) {
        deleteBtn.style.display = 'inline-flex';
    }

    console.log('[Dashboard] Exited delete mode');
}

/**
 * Handle checkbox changes (purely for UI feedback)
 */
function handleCheckboxChange(event) {
    // You could add visual feedback here if needed
    console.log(`[Dashboard] Checkbox toggled for trip: ${event.target.dataset.tripId}`);
}

/**
 * Collect selected draft trip IDs and send deletion request to backend
 */
async function confirmDeletion() {
    // Get all checked checkboxes
    const selectedCheckboxes = Array.from(document.querySelectorAll('.trip-checkbox:checked'));
    const selectedTripIds = selectedCheckboxes.map(checkbox => parseInt(checkbox.dataset.tripId));

    if (selectedTripIds.length === 0) {
        alert('Please select at least one draft trip to delete.');
        return;
    }

    const confirmation = confirm(
        `Are you sure you want to delete ${selectedTripIds.length} draft trip${selectedTripIds.length !== 1 ? 's' : ''}? This action cannot be undone.`
    );

    if (!confirmation) return;

    try {
        let ok;
        let data;

        if (typeof window.apiPostJson === 'function') {
            const result = await window.apiPostJson('/api/delete-draft-trips', { trip_ids: selectedTripIds });
            ok = result.ok;
            data = result.data;
        } else {
            const response = await fetch('/api/delete-draft-trips', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    trip_ids: selectedTripIds
                })
            });

            ok = response.ok;
            data = await response.json();
        }

        if (!ok) {
            throw new Error((data && data.error) || 'Failed to delete trips');
        }

        // Success — reload the page to reflect changes
        console.log('[Dashboard] Successfully deleted draft trips:', selectedTripIds);
        alert('Draft trips deleted successfully!');

        // Reload the trips list
        exitDeleteMode();
        loadTrips();

    } catch (error) {
        console.error('[Dashboard] Deletion Error:', error);
        alert(`Error: ${error.message}`);
    }
}

// ──────────────────────────────────────────────
//  INIT
// ──────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    loadTrips();

    // Attach event listeners for delete mode
    const deleteBtn = document.getElementById('btn-delete-drafts');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', enterDeleteMode);
    }

    const confirmBtn = document.getElementById('btn-confirm-deletion');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', confirmDeletion);
    }

    const cancelBtn = document.getElementById('btn-cancel-deletion');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', exitDeleteMode);
    }

});
