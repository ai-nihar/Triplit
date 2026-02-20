/**
 * ===================================================================
 *  SHARED REUSABLE COMPONENT: createLocationCard(loc)
 * ===================================================================
 *
 *  Used by: Home page, Explore page, Wishlist page
 *
 *  Accepts a location object with keys matching the MySQL schema:
 *    { location_id, name, locality, region, category, image_url }
 *
 *  Returns an HTML string for one card.
 *
 *  The "Add Trip" button opens a trip picker modal.
 * ===================================================================
 */

function createLocationCard(loc) {
    const imgSrc = loc.image_url
        ? loc.image_url
        : `https://via.placeholder.com/300x200?text=${encodeURIComponent(loc.name)}`;

    const locationText = [loc.locality, loc.region]
        .filter(Boolean)
        .join(', ') || 'India';

    const category = loc.category || 'Destination';

    // Icon mapping for common categories
    const iconMap = {
        'heritage': 'fa-landmark',
        'spiritual': 'fa-place-of-worship',
        'beach': 'fa-umbrella-beach',
        'mountain': 'fa-mountain-sun',
        'nature': 'fa-leaf',
        'adventure': 'fa-person-hiking',
        'destination': 'fa-location-dot',
    };
    const icon = iconMap[category.toLowerCase()] || 'fa-location-dot';

    return `
        <div class="category-card"
             data-id="${loc.location_id}"
             data-name="${loc.name}"
             data-img="${imgSrc}"
             data-locality="${loc.locality || ''}"
             data-category="${category}"
             data-region="${loc.region || 'Unknown'}"
             data-description="${(loc.description || '').replace(/"/g, '&quot;')}">
            <div class="card-img-wrapper">
                <div class="category-badge">
                    <i class="fa-solid ${icon}"></i> ${category}
                </div>
                <img src="${imgSrc}"
                     alt="${loc.name}"
                     loading="lazy"
                     onerror="this.src='https://via.placeholder.com/300x200?text=${encodeURIComponent(loc.name)}'">
                <button class="wishlist-btn" onclick="toggleWishlist(event, this)">
                    <i class="fa-regular fa-heart"></i>
                </button>
            </div>
            <div class="card-info p-3">
                <h5 class="fw-bold mb-1">${loc.name}</h5>
                <p class="text-muted small text-truncate-2"
                   style="height: 40px; overflow: hidden;
                          -webkit-line-clamp: 2; display: -webkit-box;
                          -webkit-box-orient: vertical;">
                    ${locationText}
                </p>
                <div class="d-flex justify-content-between align-items-center mt-3">
                    <button class="add-trip-btn"
                            data-location-id="${loc.location_id}"
                            onclick="handleAddToTrip(event, this)">
                        Add Trip
                    </button>
                    <a href="javascript:void(0)"
                       onclick="openLocationDetail && openLocationDetail('${loc.name.replace(/'/g, "\\'")}')"
                       class="see-more-link">See more <i class="fa-solid fa-chevron-right"></i></a>
                </div>
            </div>
        </div>`;
}

/**
 *  HELPER: Render an array of locations into a container
 *  @param {Array}  locations   — array of location objects
 *  @param {String} containerId — the DOM id to fill
 *  @param {String} emptyMsg    — message when list is empty
 */
function renderLocationCards(locations, containerId, emptyMsg) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!locations || locations.length === 0) {
        container.innerHTML = `
            <div class="empty-wishlist" style="grid-column: 1 / -1;">
                <i class="fa-regular fa-face-frown"></i>
                <h2 class="fw-bold">${emptyMsg || 'No locations available at the moment.'}</h2>
                <p class="text-muted">Try exploring new destinations!</p>
                <button onclick="window.location.href='/explore'"
                        class="search-btn mt-3" style="max-width: 250px;">
                    Explore Destinations
                </button>
            </div>`;
        return;
    }

    container.innerHTML = locations.map(createLocationCard).join('');

    // Sync wishlist heart icons after rendering
    if (typeof syncHeartIcons === 'function') {
        syncHeartIcons();
    }
}

/**
 * BUG FIX #2: Handle "Add to Trip" button click
 * Extracts location ID from the button's data-location-id attribute
 * and navigates to the dashboard or appropriate page.
 * @param {Event} event - The click event
 * @param {HTMLElement} button - The button element that was clicked
 */
function handleAddToTrip(event, button) {
    event.preventDefault();
    event.stopPropagation();

    const locationId = button.getAttribute('data-location-id');
    if (!locationId || locationId === 'null' || locationId === 'undefined') {
        console.error('[Add to Trip] ERROR: location ID is missing or invalid!', {
            locationId,
            buttonHTML: button.outerHTML
        });
        alert('Error: Location ID not found. Please try again.');
        return;
    }

    if (typeof openTripPickerForLocation === 'function') {
        openTripPickerForLocation(parseInt(locationId));
        return;
    }

    // Fallback (should not happen)
    alert('Trip picker is not available on this page.');
}


// ===================================================================
// Add-to-Trip Modal (shared across Explore/Home/Wishlist)
// ===================================================================

let tripPickerInjected = false;
let tripPickerLocationId = null;
let tripPickerSelectedTripId = null;

function _tripPickerNotify(msg) {
    if (typeof showToast === 'function') {
        showToast(msg, 'success');
        return;
    }
    alert(msg);
}

async function _apiGetJson(url) {
    if (typeof window.apiGetJson === 'function') {
        const result = await window.apiGetJson(url, {
            cache: 'no-store',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        });
        if (!result.ok) {
            const msg = (result.data && (result.data.error || result.data.message)) || `HTTP ${result.status}`;
            throw new Error(msg);
        }
        if (!result.data) {
            throw new Error('Failed to load trips (not signed in?)');
        }
        return result.data;
    }
    const res = await fetch(url, {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const ct = (res.headers.get('content-type') || '').toLowerCase();
    if (!ct.includes('application/json')) {
        throw new Error('Failed to load trips (not signed in?)');
    }
    return await res.json();
}

async function _apiPostJson(url, body) {
    if (typeof window.apiPostJson === 'function') {
        const result = await window.apiPostJson(url, body);
        if (!result.ok) {
            const msg = (result.data && (result.data.error || result.data.message)) || `HTTP ${result.status}`;
            throw new Error(msg);
        }
        return result.data;
    }
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const msg = (data && (data.error || data.message)) || `HTTP ${res.status}`;
        throw new Error(msg);
    }
    return data;
}

function ensureTripPickerModal() {
    if (tripPickerInjected) return;
    tripPickerInjected = true;

    const html = `
    <div class="trip-pick-overlay" id="tripPickOverlay" aria-hidden="true">
      <div class="trip-pick-modal" role="dialog" aria-modal="true">
        <div class="trip-pick-header">
          <h3 class="trip-pick-title">Add to Trip</h3>
          <button class="trip-pick-close" id="tripPickClose" type="button" title="Close">×</button>
        </div>
        <div class="trip-pick-body">
          <div class="trip-pick-section">
            <div class="trip-pick-subtitle">Choose a draft trip</div>
            <div class="trip-pick-list" id="tripPickList">
              <div class="trip-pick-loading" id="tripPickLoading">Loading your draft trips…</div>
            </div>
          </div>

          <div class="trip-pick-divider"></div>

          <div class="trip-pick-section">
            <div class="trip-pick-subtitle">Or create a new trip</div>
            <input class="trip-pick-input" id="tripPickNewName" type="text" placeholder="Trip name (optional)" />
            <button class="trip-pick-primary" id="tripPickCreateBtn" type="button">Create trip + add</button>
          </div>
        </div>
        <div class="trip-pick-footer">
          <button class="trip-pick-secondary" id="tripPickCancelBtn" type="button">Cancel</button>
          <button class="trip-pick-primary" id="tripPickAddBtn" type="button" disabled>Add to selected trip</button>
        </div>
      </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);

    const overlay = document.getElementById('tripPickOverlay');
    const closeBtn = document.getElementById('tripPickClose');
    const cancelBtn = document.getElementById('tripPickCancelBtn');

    function close() {
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
        tripPickerLocationId = null;
        tripPickerSelectedTripId = null;
        const addBtn = document.getElementById('tripPickAddBtn');
        if (addBtn) addBtn.disabled = true;
    }

    closeBtn.addEventListener('click', close);
    cancelBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) close();
    });

    document.getElementById('tripPickAddBtn').addEventListener('click', async () => {
        if (!tripPickerLocationId || !tripPickerSelectedTripId) return;
        try {
            await _apiPostJson('/api/trips/suggest-location', {
                trip_id: tripPickerSelectedTripId,
                location_id: tripPickerLocationId,
            });
            _tripPickerNotify('Added to trip suggestions');
            close();
        } catch (err) {
            alert(err.message || String(err));
        }
    });

    document.getElementById('tripPickCreateBtn').addEventListener('click', async () => {
        if (!tripPickerLocationId) return;
        const name = (document.getElementById('tripPickNewName').value || '').trim();
        try {
            // Switching to "create new" means we should clear any selected draft-trip radio.
            tripPickerSelectedTripId = null;
            document.querySelectorAll('input[name="tripPick"]').forEach(r => { r.checked = false; });
            const addBtn = document.getElementById('tripPickAddBtn');
            if (addBtn) addBtn.disabled = true;

            const data = await _apiPostJson('/api/trips/quick-create', {
                location_id: tripPickerLocationId,
                trip_name: name,
            });
            if (data && data.redirect) {
                window.location.href = data.redirect;
                return;
            }
            _tripPickerNotify('Trip created');
            close();
        } catch (err) {
            alert(err.message || String(err));
        }
    });

    // Focusing on "create new" clears any selected draft trip.
    const newNameInput = document.getElementById('tripPickNewName');
    if (newNameInput) {
        newNameInput.addEventListener('focus', () => {
            tripPickerSelectedTripId = null;
            document.querySelectorAll('input[name="tripPick"]').forEach(r => { r.checked = false; });
            const addBtn = document.getElementById('tripPickAddBtn');
            if (addBtn) addBtn.disabled = true;
        });
    }
}

async function openTripPickerForLocation(locationId) {
    ensureTripPickerModal();

    tripPickerLocationId = locationId;
    tripPickerSelectedTripId = null;

    const overlay = document.getElementById('tripPickOverlay');
    const list = document.getElementById('tripPickList');
    const addBtn = document.getElementById('tripPickAddBtn');
    if (addBtn) addBtn.disabled = true;

    let loading = document.getElementById('tripPickLoading');
    if (!loading) {
        loading = document.createElement('div');
        loading.className = 'trip-pick-loading';
        loading.id = 'tripPickLoading';
        loading.textContent = 'Loading your draft trips…';
    }

    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
    list.replaceChildren(loading);
    loading.style.display = 'block';

    try {
        // no-store + cache-busting to avoid stale "no draft trips" responses
        const tripsData = await _apiGetJson(`/api/my-trips?t=${Date.now()}`);
        const drafts = (tripsData && tripsData.draft_trips) ? tripsData.draft_trips : [];

        loading.style.display = 'none';
        list.replaceChildren();

        if (!drafts.length) {
            list.innerHTML = `<div class="trip-pick-empty">No draft trips yet. Create a new trip below.</div>`;
            return;
        }

        drafts.forEach(t => {
            const tripId = t.trip_id;
            const name = t.trip_name || `Trip #${tripId}`;
            const meta = [t.start_region, t.end_region].filter(Boolean).join(' → ');
            const row = document.createElement('label');
            row.className = 'trip-pick-row';
            row.innerHTML = `
              <input type="radio" name="tripPick" value="${tripId}">
              <div class="trip-pick-row-main">
                <div class="trip-pick-row-title">${name}</div>
                <div class="trip-pick-row-meta">${meta || 'Draft trip'}</div>
              </div>`;
            // Make selection deselectable: clicking selected row again clears it.
            row.addEventListener('click', (e) => {
                e.preventDefault();
                const input = row.querySelector('input');
                const wasChecked = !!input.checked;

                document.querySelectorAll('input[name="tripPick"]').forEach(r => { r.checked = false; });

                if (wasChecked) {
                    tripPickerSelectedTripId = null;
                    if (addBtn) addBtn.disabled = true;
                    return;
                }

                input.checked = true;
                tripPickerSelectedTripId = parseInt(tripId);
                if (addBtn) addBtn.disabled = false;
            });
            list.appendChild(row);
        });
    } catch (err) {
        loading.style.display = 'none';
        list.innerHTML = `<div class="trip-pick-empty">Failed to load trips: ${String(err.message || err)}</div>`;
    }
}
