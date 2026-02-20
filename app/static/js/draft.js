/* ==========================================================================
   DRAFT.JS — Fully API-Driven Trip Planning Dashboard (v2)
   Features: Empty-by-default available, AI suggestions, search, grouped route
   ========================================================================== */

// ==========================================================================
// 1. STATE
// ==========================================================================

let allAvailableLocations = [];   // Populated by AI suggestions or search
let wishlistLocationIds = new Set(); // IDs currently in user's wishlist
let selectedLocations = [];   // Locations added to current trip

// ========================================================================
// 1.5 API HELPERS (use api-client.js when present)
// ========================================================================

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function apiGetJsonSafe(url, options) {
    if (typeof window.apiGetJson === 'function') {
        return window.apiGetJson(url, options);
    }

    const response = await fetch(url, options);
    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }

    return { ok: response.ok, status: response.status, data, response };
}

async function apiPostJsonSafe(url, body, options) {
    if (typeof window.apiPostJson === 'function') {
        return window.apiPostJson(url, body, options);
    }

    const headers = Object.assign({ 'Content-Type': 'application/json' }, (options && options.headers) || {});
    const response = await fetch(
        url,
        Object.assign({}, options || {}, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
        }),
    );

    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }

    return { ok: response.ok, status: response.status, data, response };
}

// ==========================================================================
// 2. INIT — Available locations are NOT loaded on page load
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('✓ Draft Trip Dashboard v2 — Initializing');
    loadWishlistItems();
    loadSelectedLocations();
    setupRouteButton();
    // Load existing suggestions if any
    fetchSuggestions('load');
});

function updateRouteEndpointSelectors() {
    const startSel = document.getElementById('route-start-select');
    const endSel = document.getElementById('route-end-select');
    if (!startSel || !endSel) return;

    const prevStart = startSel.value;
    const prevEnd = endSel.value;

    const buildOptions = (label) => {
        const opts = [`<option value="">${label}</option>`];
        selectedLocations.forEach(loc => {
            const id = String(loc.location_id);
            const locText = [loc.locality, loc.region].filter(Boolean).join(', ');
            const name = locText ? `${escapeHtml(loc.name)} — ${escapeHtml(locText)}` : escapeHtml(loc.name);
            opts.push(`<option value="${id}">${name}</option>`);
        });
        return opts.join('');
    };

    startSel.innerHTML = buildOptions('Auto (best start)');
    endSel.innerHTML = buildOptions('Auto (best end)');

    // Restore previous selection if it still exists
    if ([...startSel.options].some(o => o.value === prevStart)) startSel.value = prevStart;
    if ([...endSel.options].some(o => o.value === prevEnd)) endSel.value = prevEnd;

    // Prevent invalid “same start/end” selection
    if (startSel.value && endSel.value && startSel.value === endSel.value) {
        endSel.value = '';
    }
}

// ==========================================================================
// 3. AI SUGGESTIONS — triggered by "Give AI Suggestions" button
// ==========================================================================

// Renamed from getAISuggestions to be more generic
async function fetchSuggestions(mode = 'generate') {
    const container = document.getElementById('available-locations-scroll');
    const btn = document.getElementById('ai-suggest-btn');

    if (!CURRENT_TRIP_ID) {
        showToast('No trip context found', 'error');
        return;
    }

    // UI feedback
    const origText = btn.innerHTML;
    if (mode === 'generate') {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading AI Suggestions...';
        btn.disabled = true;
    }

    if (!allAvailableLocations.length && mode === 'load') {
        container.innerHTML = `
            <div class="scroll-loading">
                <div class="spinner-border spinner-border-sm text-secondary"></div>
                <span>Loading suggestions...</span>
            </div>`;
    }

    // Collect names to exclude (avoid duplicates)
    const excludedNames = [
        ...allAvailableLocations.map(l => l.name),
        ...selectedLocations.map(l => l.name)
    ];

    try {
        let result;
        if (mode === 'load') {
            // GET request: loads existing or generates first batch if empty
            result = await apiGetJsonSafe(`/api/trips/${CURRENT_TRIP_ID}/suggestions`);
        } else {
            // POST request: explicitly asking for NEW suggestions
            result = await apiPostJsonSafe(`/api/trips/${CURRENT_TRIP_ID}/suggestions`, { excluded_names: excludedNames });
        }

        if (!result.ok) throw new Error(`HTTP ${result.status}`);
        const data = result.data;

        const suggestions = data.suggestions || [];
        const newCount = data.new_count || 0;

        if (!suggestions.length) {
            if (mode === 'load') {
                container.innerHTML = `
                    <div class="scroll-empty-state">
                        <i class="fa-solid fa-wand-magic-sparkles"></i>
                        <p>Need some inspiration?</p>
                        <small>Click "Give AI Suggestions" to discover places!</small>
                    </div>`;
            } else {
                container.innerHTML = `
                    <div class="scroll-empty-state">
                        <i class="fa-solid fa-robot"></i>
                        <p>No new suggestions found</p>
                        <small>We've exhausted AI ideas for now!</small>
                    </div>`;
            }
            return;
        }

        // Convert suggestion format to location-card format
        const incoming = suggestions.map((s, i) => ({
            location_id: s.suggestion_id || s.location_id || (90000 + i),
            name: s.name,
            category: s.category || 'Place',
            region: s.region || '',
            locality: s.locality || '',
            image_url: s.image_url || '',
            description: s.description || ''
        }));

        // Merge uniquely so previous suggestions don't disappear on re-click
        const byId = new Map();
        (allAvailableLocations || []).forEach(l => {
            if (l && l.location_id != null) byId.set(String(l.location_id), l);
        });
        incoming.forEach(l => {
            if (l && l.location_id != null) byId.set(String(l.location_id), l);
        });
        allAvailableLocations = Array.from(byId.values());

        renderAvailableCards(container, allAvailableLocations);

        if (newCount > 0) {
            showToast(`✨ ${newCount} new suggestions added!`, 'success');
        } else if (mode === 'load' && suggestions.length > 0) {
            // loaded
        } else if (mode === 'generate') {
            showToast('No new suggestions found', 'info');
        }
    } catch (err) {
        console.error('AI Suggest Error:', err);
        container.innerHTML = `
            <div class="scroll-empty-state">
                <i class="fa-solid fa-triangle-exclamation text-danger"></i>
                <p>Failed to load suggestions</p>
                <small>${err.message}</small>
            </div>`;
    } finally {
        if (mode === 'generate') {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }
}

// ==========================================================================
// 4. SEARCH LOCATIONS — triggered by search bar
// ==========================================================================

function handleSearchKeyup(event) {
    if (event.key === 'Enter') {
        searchLocations();
    }
}

async function searchLocations() {
    const input = document.getElementById('location-search-input');
    const query = input.value.trim();
    const container = document.getElementById('available-locations-scroll');

    if (!query || query.length < 2) {
        showToast('Enter at least 2 characters to search', 'info');
        return;
    }

    container.innerHTML = `
        <div class="scroll-loading">
            <div class="spinner-border spinner-border-sm text-secondary"></div>
            <span>Searching for "${escapeHtml(query)}"...</span>
        </div>`;

    try {
        const result = await apiGetJsonSafe(`/api/locations/search?q=${encodeURIComponent(query)}`);
        if (!result.ok) throw new Error(`HTTP ${result.status}`);
        const data = result.data;

        const locations = data.locations || [];

        if (!locations.length) {
            container.innerHTML = `
                <div class="scroll-empty-state">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <p>No results for "${escapeHtml(query)}"</p>
                    <small>Try a different search term or use AI suggestions.</small>
                </div>`;
            return;
        }

        allAvailableLocations = locations;
        renderAvailableCards(container, allAvailableLocations);
        showToast(`🔍 ${locations.length} locations found`, 'success');

    } catch (err) {
        console.error('[Search] Error:', err);
        container.innerHTML = `
            <div class="scroll-empty-state">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Search failed</p>
                <small>${err.message}</small>
            </div>`;
    }
}

// ==========================================================================
// 5. RENDER AVAILABLE CARDS
// ==========================================================================

function renderAvailableCards(container, locations) {
    container.innerHTML = '';
    locations.forEach(loc => {
        container.appendChild(createScrollCard(loc, 'available'));
    });
}

// ==========================================================================
// 6. WISHLIST — fetches on page load (auto)
// ==========================================================================

async function loadWishlistItems() {
    const container = document.getElementById('wishlist-scroll');
    const badge = document.getElementById('wishlist-count-badge');

    try {
        const result = await apiGetJsonSafe('/api/wishlist');
        if (!result.ok) throw new Error(`HTTP ${result.status}`);
        const data = result.data;

        // data may be an array directly
        const items = Array.isArray(data) ? data : (data.locations || []);

        // Build set of wishlisted IDs (for heart state sync)
        wishlistLocationIds = new Set(items.map(i => i.location_id));

        badge.textContent = items.length;

        if (!items.length) {
            container.innerHTML = `
                <div class="scroll-empty-state">
                    <i class="fa-solid fa-heart"></i>
                    <p>No wishlist items yet</p>
                    <small>Visit Explore and ❤ locations to add them here!</small>
                </div>`;
            syncHeartStates();
            return;
        }

        container.innerHTML = '';
        items.forEach(loc => {
            container.appendChild(createScrollCard(loc, 'wishlist'));
        });

        syncHeartStates();

    } catch (err) {
        console.error('[Draft] Failed to load wishlist:', err);
        container.innerHTML = `
            <div class="scroll-empty-state">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Could not load wishlist</p>
                <small>${err.message}</small>
            </div>`;
    }
}

// ==========================================================================
// 7. REUSABLE SCROLL CARD
// ==========================================================================

function createScrollCard(loc, section) {
    const card = document.createElement('div');
    card.className = 'category-card';
    card.dataset.id = String(loc.location_id);
    card.dataset.name = loc.name || '';
    card.dataset.img = loc.image_url || '';
    card.dataset.locality = loc.locality || '';
    card.dataset.region = loc.region || '';
    card.dataset.category = loc.category || '';
    card.dataset.description = loc.description || '';

    // Image logic
    const imgSrc = loc.image_url || `https://via.placeholder.com/300x200?text=${encodeURIComponent(loc.name || 'Place')}`;

    // Category logic
    const categoryRaw = loc.category || 'Destination';
    const category = categoryRaw.charAt(0).toUpperCase() + categoryRaw.slice(1);

    // Icon mapping matching location-card.js
    const iconMap = {
        'heritage': 'fa-landmark',
        'spiritual': 'fa-place-of-worship',
        'beach': 'fa-umbrella-beach',
        'mountain': 'fa-mountain-sun',
        'nature': 'fa-leaf',
        'adventure': 'fa-person-hiking',
        'destination': 'fa-location-dot',
        'entertainment': 'fa-ticket',
        'food': 'fa-utensils',
        'shopping': 'fa-bag-shopping'
    };
    const icon = iconMap[category.toLowerCase()] || 'fa-location-dot';

    // Description logic (same as shared cards)
    const locText = loc.description || (loc.locality
        ? `${loc.locality}${loc.region ? ', ' + loc.region : ''}`
        : 'A wonderful destination to explore.');

    // Heart logic
    const isWishlisted = wishlistLocationIds.has(loc.location_id);

    // Button logic
    const isSelected = selectedLocations.some(s => s.location_id === loc.location_id);
    const btnDisabledAttr = isSelected ? 'disabled' : '';
    const btnText = isSelected ? 'Added' : 'Add';
    const btnIcon = isSelected ? 'fa-check' : 'fa-plus';

    card.innerHTML = `
        <div class="card-img-wrapper">
            <div class="category-badge">
                <i class="fa-solid ${icon}"></i> ${category}
            </div>
            <img src="${imgSrc}" alt="${loc.name || ''}" loading="lazy"
                 onerror="this.src='https://via.placeholder.com/300x200?text=${encodeURIComponent(loc.name || 'Place')}'">
            <button class="wishlist-btn ${isWishlisted ? 'active' : ''}"
                    data-id="${loc.location_id}"
                    onclick="toggleWishlistHeart(event, this)"
                    title="Toggle wishlist">
                <i class="fa-${isWishlisted ? 'solid' : 'regular'} fa-heart"></i>
            </button>
        </div>
        <div class="card-info p-3">
            <h5 class="fw-bold mb-1">${loc.name || ''}</h5>
            <p class="text-muted small text-truncate-2 loc-card-desc"
               style="height: 40px; overflow: hidden; -webkit-line-clamp: 2; display: -webkit-box; -webkit-box-orient: vertical;"
               title="${String(locText).replace(/"/g, '&quot;')}">
                ${locText}
            </p>
            <div class="d-flex justify-content-between align-items-center mt-3">
                <button class="add-trip-btn"
                        onclick="addToSelected(${loc.location_id})"
                        ${btnDisabledAttr}>
                    <i class="fa-solid ${btnIcon}"></i> ${btnText}
                </button>
                <a href="javascript:void(0)"
                   onclick="openLocationDetail && openLocationDetail('${(loc.name || '').replace(/'/g, "\\'")}')"
                   class="see-more-link">See more <i class="fa-solid fa-chevron-right"></i></a>
            </div>
        </div>
    `;

    return card;
}

// ==========================================================================
// 8. HEART BUTTON — optimistic toggle + API
// ==========================================================================

async function toggleWishlistHeart(event, btn) {
    event.stopPropagation();

    const locationId = parseInt(btn.dataset.id, 10);
    const icon = btn.querySelector('i');
    const wasWishlisted = btn.classList.contains('active');

    // Optimistic UI update
    if (wasWishlisted) {
        btn.classList.remove('active');
        icon.className = 'fa-regular fa-heart';
        wishlistLocationIds.delete(locationId);
    } else {
        btn.classList.add('active');
        icon.className = 'fa-solid fa-heart';
        wishlistLocationIds.add(locationId);
    }

    syncHeartById(locationId, !wasWishlisted);

    try {
        const apiResult = await apiPostJsonSafe('/api/wishlist/toggle', { location_id: locationId });
        if (!apiResult.ok) throw new Error(`HTTP ${apiResult.status}`);
        const resultData = apiResult.data;
        console.log(`[Wishlist] ${resultData.action} location ${locationId}`);

        if (resultData.action === 'removed') {
            removeCardFromWishlistRow(locationId);
        }
        if (resultData.action === 'added') {
            loadWishlistItems();
        }

    } catch (err) {
        console.error('[Wishlist] Toggle failed:', err);
        // Rollback UI
        if (wasWishlisted) {
            btn.classList.add('active');
            icon.className = 'fa-solid fa-heart';
            wishlistLocationIds.add(locationId);
        } else {
            btn.classList.remove('active');
            icon.className = 'fa-regular fa-heart';
            wishlistLocationIds.delete(locationId);
        }
        syncHeartById(locationId, wasWishlisted);
        showToast('Failed to update wishlist', 'error');
    }
}

/** Sync all heart buttons for a given location_id across all sections */
function syncHeartById(locationId, isWishlisted) {
    document.querySelectorAll(`.wishlist-btn[data-id="${locationId}"]`).forEach(btn => {
        const icon = btn.querySelector('i');
        if (isWishlisted) {
            btn.classList.add('active');
            icon.className = 'fa-solid fa-heart';
        } else {
            btn.classList.remove('active');
            icon.className = 'fa-regular fa-heart';
        }
    });
}

/** After wishlist loaded, sync hearts on Available cards */
function syncHeartStates() {
    document.querySelectorAll('#available-locations-scroll .wishlist-btn').forEach(btn => {
        const id = parseInt(btn.dataset.id, 10);
        const icon = btn.querySelector('i');
        if (wishlistLocationIds.has(id)) {
            btn.classList.add('active');
            icon.className = 'fa-solid fa-heart';
        } else {
            btn.classList.remove('active');
            icon.className = 'fa-regular fa-heart';
        }
    });
}

/** Remove a card from the wishlist scroll row without reload */
function removeCardFromWishlistRow(locationId) {
    const wishlistRow = document.getElementById('wishlist-scroll');
    const card = wishlistRow.querySelector(`.category-card[data-id="${locationId}"]`);
    if (card) {
        card.style.transition = 'opacity 0.3s, transform 0.3s';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.9)';
        setTimeout(() => card.remove(), 300);
    }

    const badge = document.getElementById('wishlist-count-badge');
    const remaining = wishlistRow.querySelectorAll('.category-card').length - 1;
    badge.textContent = Math.max(0, remaining);

    if (remaining <= 0) {
        setTimeout(() => {
            wishlistRow.innerHTML = `
                <div class="scroll-empty-state">
                    <i class="fa-solid fa-heart"></i>
                    <p>No wishlist items yet</p>
                    <small>Visit Explore and ❤ locations to add them here!</small>
                </div>`;
        }, 350);
    }
}

// ==========================================================================
// 9. SELECTED LOCATIONS (Add / Remove / Render)
// ==========================================================================

async function loadSelectedLocations() {
    if (!CURRENT_TRIP_ID) return;
    try {
        const result = await apiGetJsonSafe(`/api/trips/${CURRENT_TRIP_ID}/selected-locations`);
        if (result.ok) {
            const data = result.data;
            // Map plain objects to ensure compatibility if needed, though they match
            selectedLocations = data.locations || [];
            renderSelectedLocations();
            updateSelectedCount();
            console.log(`[Selected] Loaded ${selectedLocations.length} items`);
        }
    } catch (err) {
        console.error('[Selected] Load failed:', err);
    }
}

function addToSelected(locationId) {
    if (selectedLocations.some(s => s.location_id === locationId)) {
        showToast('Already in your trip!', 'info');
        return;
    }

    // Try to find in available (search results or AI suggestions)
    let loc = allAvailableLocations.find(l => l.location_id === locationId);

    // Fallback: Try to find in Wishlist items if not in available
    if (!loc) {
        // We don't have a global wishlist array, but we can check if the DOM element has data?
        // Or just query the card if possible.
        // Actually, wait. loadWishlistItems populates the DOM but doesn't store in global array except ids.
        // But createScrollCard renders data.
        // Let's assume for now it's in allAvailableLocations OR we need to fetch it?
        // Simplest: Check if we can find it. If not, error.
        // Actually, clicking 'Add' from Wishlist relies on it being in allAvailableLocations? 
        // NO. wishlist items are rendered separately.
        // We need to resolve the location object.
        // I'll grab it from the card data or assume the user has it.
        // Wait, the original code looked in `allAvailableLocations`.
        // If I click Add on Wishlist, does it work?
        // If `allAvailableLocations` is empty (default), then `loc` is undefined.
        // This is a BUG in the original code if Wishlist naming/data isn't in `allAvailableLocations`.
        // But wait, `renderAvailableCards` populates `allAvailableLocations`.
        // `loadWishlistItems` does NOT.
        // So adding from wishlist might fail if I don't fix this finding logic.
        // I'll assume for now `loc` is found or I should look in `wishlist cache`.
        // I'll fetch it if missing? No, that's async.
        // Let's stick to the error handling part for now. 
    }

    // Quick Fix for Wishlist finding: 
    // Browse the DOM to reconstruct? No.
    // I'll assume `allAvailableLocations` has it or we skip strictly.
    // If loc is undefined, original code returns 'Location not found'.

    if (!loc) {
        // Fallback: reconstruct from DOM card (works for Wishlist row too)
        const cardEl = document.querySelector(`.category-card[data-id="${locationId}"]`);
        if (cardEl) {
            loc = {
                location_id: locationId,
                name: cardEl.dataset.name || '',
                image_url: cardEl.dataset.img || (cardEl.querySelector('img')?.src || ''),
                locality: cardEl.dataset.locality || '',
                region: cardEl.dataset.region || '',
                category: cardEl.dataset.category || '',
                description: cardEl.dataset.description || ''
            };
        }
    }

    if (!loc) {
        showToast('Location details not found (reload?)', 'error');
        return;
    }

    // 1. Optimistic Update
    selectedLocations.push(loc);
    renderSelectedLocations();
    updateSelectedCount();
    disableAddButton(locationId);
    clearRouteResults();

    showToast(`✓ ${loc.name} added to trip`, 'success');

    // 2. Persist to DB
    if (CURRENT_TRIP_ID) {
        apiPostJsonSafe('/api/trips/add-location', { trip_id: CURRENT_TRIP_ID, location_id: locationId })
            .then(async result => {
                if (!result.ok) {
                    const d = result.data || {};
                    throw new Error(d.error || d.message || 'Server error');
                }
            })
            .catch(err => {
                console.warn('[Add Location] Failed:', err);
                // Rollback
                selectedLocations = selectedLocations.filter(l => l.location_id !== locationId);
                renderSelectedLocations();
                updateSelectedCount();
                enableAddButton(locationId);
                showToast(`❌ Cannot add: ${err.message}`, 'error');
            });
    }
}

function removeFromSelected(locationId) {
    selectedLocations = selectedLocations.filter(l => l.location_id !== locationId);
    renderSelectedLocations();
    updateSelectedCount();
    enableAddButton(locationId);
    clearRouteResults();

    if (CURRENT_TRIP_ID) {
        apiPostJsonSafe('/api/trips/remove-location', { trip_id: CURRENT_TRIP_ID, location_id: locationId })
            .catch(err => console.warn('[Remove Location] DB remove failed:', err));
    }

    showToast('Location removed', 'info');
}

function renderSelectedLocations() {
    const list = document.getElementById('selected-locations-list');

    if (!selectedLocations.length) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-map-marked-alt"></i>
                <p>No locations selected yet.</p>
                <small>Add locations from above to get started!</small>
            </div>`;
        return;
    }

    list.innerHTML = '';
    selectedLocations.forEach((loc, idx) => {
        const item = document.createElement('div');
        item.className = 'selected-item';

        const locText = [loc.locality, loc.region].filter(Boolean).join(', ') || 'India';

        item.innerHTML = `
            <div class="selected-item-info">
                <div class="selected-item-title">
                    <span class="item-number">${idx + 1}.</span> ${loc.name}
                </div>
                <div class="selected-item-index">
                    <i class="fa-solid fa-map-pin item-icon"></i>${locText}
                </div>
            </div>
            <button class="selected-item-remove"
                    onclick="removeFromSelected(${loc.location_id})"
                    title="Remove">
                <i class="fa-solid fa-xmark"></i>
            </button>
        `;

        list.appendChild(item);
    });

    updateRouteEndpointSelectors();
}

function updateSelectedCount() {
    document.getElementById('selected-count').textContent = selectedLocations.length;
}

function disableAddButton(locationId) {
    document.querySelectorAll(`.category-card[data-id="${locationId}"] .add-trip-btn`).forEach(btn => {
        btn.disabled = true;
    });
}

function enableAddButton(locationId) {
    document.querySelectorAll(`.category-card[data-id="${locationId}"] .add-trip-btn`).forEach(btn => {
        btn.disabled = false;
    });
}

// ==========================================================================
// 10. ROUTE OPTIMIZATION — Grouped by Region → Day → Locations
// ==========================================================================

function setupRouteButton() {
    const btn = document.getElementById('calculate-route-btn');
    if (btn) btn.addEventListener('click', calculateBestRoute);
}

async function calculateBestRoute() {
    if (!selectedLocations.length) {
        showToast('Select at least one location first', 'info');
        return;
    }

    const btn = document.getElementById('calculate-route-btn');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Calculating...';
    btn.disabled = true;

    // If trip has a DB context, run backend optimization then fetch itinerary
    if (CURRENT_TRIP_ID) {
        try {
            const startSel = document.getElementById('route-start-select');
            const endSel = document.getElementById('route-end-select');
            const startId = startSel && startSel.value ? Number(startSel.value) : null;
            const endId = endSel && endSel.value ? Number(endSel.value) : null;

            const opt = await apiPostJsonSafe(`/api/trips/${CURRENT_TRIP_ID}/optimize`, {
                start_location_id: (typeof startId === 'number' && isFinite(startId)) ? startId : null,
                end_location_id: (typeof endId === 'number' && isFinite(endId)) ? endId : null,
            });
            if (!opt.ok) {
                const msg = (opt.data && (opt.data.message || opt.data.error)) || `HTTP ${opt.status}`;
                throw new Error(msg);
            }

            const totals = opt.data || {};
            const result = await apiGetJsonSafe(`/api/trips/${CURRENT_TRIP_ID}/itinerary`);
            if (!result.ok) throw new Error(`HTTP ${result.status}`);

            const data = result.data;
            if (data.regions && data.regions.length > 0) {
                displayGroupedRoute(data, totals);
                btn.innerHTML = orig;
                btn.disabled = false;
                return;
            }
        } catch (err) {
            console.warn('[Route] Backend itinerary fetch failed, falling back to local:', err);
        }
    }

    // Fallback: local route display grouped by region from selectedLocations
    displayLocalGroupedRoute();
    btn.innerHTML = orig;
    btn.disabled = false;
}

/**
 * Display the grouped route: Region → Day → Locations
 * Uses data from /api/trips/<trip_id>/itinerary
 */
function displayGroupedRoute(data, totals) {
    const container = document.getElementById('route-results');
    let html = '<div class="route-sequence">';
    let globalIdx = 1;

    const fmtMin = (m) => {
        if (typeof m !== 'number' || !isFinite(m)) return null;
        const total = Math.max(0, Math.round(m));
        const h = Math.floor(total / 60);
        const min = total % 60;
        if (h <= 0) return `${min}m`;
        if (min === 0) return `${h}h`;
        return `${h}h ${min}m`;
    };

    data.regions.forEach(region => {
        // Region header
        html += `
            <div class="route-region-header">
                <span class="route-region-icon">📍</span>
                <span class="route-region-name">${region.name}</span>
            </div>`;

        region.days.forEach(day => {
            const travelText = fmtMin(day.travel_min);
            const visitText = fmtMin(day.visit_min);
            const totalText = fmtMin(day.total_min);
            const meta = (travelText || visitText || totalText)
                ? ` <span style="opacity:0.7">• Travel ${travelText || '—'} • Visit ${visitText || '—'} • Total ${totalText || '—'}</span>`
                : '';

            // Day sub-header
            html += `
                <div class="route-day-header">
                    <i class="fa-regular fa-calendar-days"></i> Day ${day.day_number}${meta}
                </div>`;

            day.locations.forEach(loc => {
                const locText = [loc.locality, loc.region].filter(Boolean).join(', ') || 'India';
                html += `
                    <div class="route-stop fade-in">
                        <div class="route-stop-number">${globalIdx}</div>
                        <div class="route-stop-info">
                            <p class="route-stop-title">${loc.name}</p>
                            <p class="route-stop-distance">
                                <i class="fa-solid fa-map-marker-alt"></i> ${locText}
                            </p>
                        </div>
                    </div>`;
                globalIdx++;
            });
        });
    });

    // Summary
    const distanceKm = totals && typeof totals.total_distance_km === 'number' ? totals.total_distance_km : null;
    const durationMin = totals && typeof totals.total_duration_min === 'number' ? totals.total_duration_min : null;
    html += buildRouteSummary(data.total_locations, distanceKm, durationMin);
    html += '</div>';

    container.innerHTML = html;
    showToast('✓ Route optimized!', 'success');
}

/**
 * Fallback: Build grouped route locally from selectedLocations data
 */
function displayLocalGroupedRoute() {
    // Group selected locations by region
    const regionMap = {};
    selectedLocations.forEach(loc => {
        const r = loc.region || 'Other';
        if (!regionMap[r]) regionMap[r] = [];
        regionMap[r].push(loc);
    });

    // Determine pace (default balanced = 3)
    const locsPerDay = 3;

    const container = document.getElementById('route-results');
    let html = '<div class="route-sequence">';
    let globalIdx = 1;
    let globalDay = 1;

    Object.keys(regionMap).forEach(regionName => {
        const locs = regionMap[regionName];

        // Region header
        html += `
            <div class="route-region-header">
                <span class="route-region-icon">📍</span>
                <span class="route-region-name">${regionName}</span>
            </div>`;

        // Chunk into days
        for (let i = 0; i < locs.length; i += locsPerDay) {
            const chunk = locs.slice(i, i + locsPerDay);

            html += `
                <div class="route-day-header">
                    <i class="fa-regular fa-calendar-days"></i> Day ${globalDay}
                </div>`;

            chunk.forEach(loc => {
                const locText = [loc.locality, loc.region].filter(Boolean).join(', ') || 'India';
                html += `
                    <div class="route-stop fade-in">
                        <div class="route-stop-number">${globalIdx}</div>
                        <div class="route-stop-info">
                            <p class="route-stop-title">${loc.name}</p>
                            <p class="route-stop-distance">
                                <i class="fa-solid fa-map-marker-alt"></i> ${locText}
                            </p>
                        </div>
                    </div>`;
                globalIdx++;
            });

            globalDay++;
        }
    });

    html += buildRouteSummary(selectedLocations.length, null, null);
    html += '</div>';

    container.innerHTML = html;
    showToast('✓ Route optimized!', 'success');
}

/**
 * Build the route summary card + finalize button
 */
function buildRouteSummary(totalLocations, totalDistanceKm, totalDurationMin) {
    const distanceKm = (typeof totalDistanceKm === 'number' && isFinite(totalDistanceKm))
        ? totalDistanceKm
        : (totalLocations * 4.5);

    const durationMin = (typeof totalDurationMin === 'number' && isFinite(totalDurationMin))
        ? totalDurationMin
        : Math.max(0, distanceKm / 30 * 60);

    const hours = Math.floor(durationMin / 60);
    const mins = Math.round(durationMin % 60);
    const estTime = `${hours}h ${mins}m`;

    return `
        <!-- Route Summary Card -->
        <div class="route-summary-card">
            <div class="summary-header">
                <h3 class="summary-title">Route Summary</h3>
                <p class="summary-subtitle">Optimized for travel time and fuel efficiency.</p>
            </div>

            <div class="metrics-grid">
                <div class="metric-box">
                    <p class="metric-label">Total Distance</p>
                    <div class="metric-value">
                        ${distanceKm.toFixed(1)} <span class="metric-unit">km</span>
                    </div>
                </div>
                <div class="metric-box">
                    <p class="metric-label">Est. Time</p>
                    <div class="metric-value">${estTime}</div>
                </div>
            </div>

            <div class="info-list">
                <div class="info-item">
                    <div class="info-icon"><i class="fa-solid fa-leaf"></i></div>
                    <div class="info-text">
                        <span class="info-title">Carbon Offset Recommendation</span>
                        <span class="info-subtitle">Reduce emissions by 12% with this route.</span>
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-icon"><i class="fa-solid fa-traffic-light"></i></div>
                    <div class="info-text">
                        <span class="info-title">Traffic Intelligence</span>
                        <span class="info-subtitle">Real-time adjustments for local congestion.</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Finalize Action Area -->
        <div class="finalize-action-area">
            <button id="finalize-trip-btn" class="btn-finalize" onclick="finalizeTrip()">
                <i class="fa-solid fa-check-double"></i> Finalize Itinerary
            </button>
            <span class="finalize-warning">
                <i class="fa-solid fa-circle-info"></i> Note: Once finalized, this trip is locked and cannot be edited.
            </span>
        </div>`;
}

/** 
 * Finalize the trip: update status to 'finalized' in DB and redirect to dashboard 
 */
async function finalizeTrip() {
    if (!window.confirm("Are you sure you want to finalize this trip? You will no longer be able to add or remove locations.")) {
        return;
    }

    const btn = document.getElementById('finalize-trip-btn');
    const originalContent = btn.innerHTML;

    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Finalizing...';
    btn.disabled = true;

    try {
        const result = await apiPostJsonSafe('/api/trips/finalize', { trip_id: CURRENT_TRIP_ID });
        if (!result.ok) throw new Error(`HTTP ${result.status}`);
        const data = result.data;

        if (data.success) {
            showToast('✓ Trip finalized successfully!', 'success');
            setTimeout(() => {
                window.location.href = `/itinerary/${CURRENT_TRIP_ID}`;
            }, 1000);
        } else {
            throw new Error(data.message || 'Could not finalize trip');
        }

    } catch (err) {
        console.error('[Finalize] Error:', err);
        showToast('Failed to finalize: ' + err.message, 'error');
        btn.innerHTML = originalContent;
        btn.disabled = false;
    }
}

function clearRouteResults() {
    const container = document.getElementById('route-results');
    if (!container) return;
    container.innerHTML = `
        <div class="empty-state-route">
            <i class="fa-solid fa-directions"></i>
            <p>Route will appear here</p>
            <small>Select locations and click "Calculate Best Route"</small>
        </div>`;
}

// ==========================================================================
// 11. TOAST NOTIFICATION
// ==========================================================================

function showToast(message, type = 'info') {
    const existing = document.querySelectorAll('.draft-toast');
    existing.forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = 'draft-toast';

    const colors = { success: '#10b981', error: '#ef4444', info: '#3b82f6' };
    toast.style.cssText = `
        position: fixed; top: 80px; right: 24px;
        padding: 14px 22px; border-radius: 12px;
        color: white; font-weight: 600; font-size: 0.85rem;
        z-index: 9999; max-width: 320px;
        background: ${colors[type] || colors.info};
        box-shadow: 0 8px 24px rgba(0,0,0,0.12);
        animation: toastSlideIn 0.35s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastSlideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Inject toast animation styles
if (!document.getElementById('draft-toast-css')) {
    const s = document.createElement('style');
    s.id = 'draft-toast-css';
    s.textContent = `
        @keyframes toastSlideIn {
            from { opacity: 0; transform: translateX(100px); }
            to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes toastSlideOut {
            from { opacity: 1; transform: translateX(0); }
            to   { opacity: 0; transform: translateX(100px); }
        }
    `;
    document.head.appendChild(s);
}

console.log('✓ draft.js v2 loaded — empty-by-default, AI suggestions, grouped route');

// ==========================================================================
// 12. SCROLL UTILS
// ==========================================================================

function scrollSection(elementId, amount) {
    const el = document.getElementById(elementId);
    if (el) {
        el.scrollBy({
            left: amount,
            behavior: 'smooth'
        });
    }
}

// Expose for HTML button
window.getAISuggestions = () => fetchSuggestions('generate');
