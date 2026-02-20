/**
 * ===================================================================
 *  Wishlist Logic — Heart toggle + sync
 * ===================================================================
 *
 *  DEPENDS ON: location-card.js (shared createLocationCard function)
 *
 *  This file handles:
 *    - Toggling the wishlist heart button (on any page with cards)
 *    - Syncing heart icon states when pages load
 *    - Persisting wishlist to both localStorage AND the DB API
 * ===================================================================
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Sync from LocalStorage immediately (fast)
    syncHeartIcons();

    // 2. Fetch real source of truth from DB and update
    fetchWishlistFromAPI();

    // 3. If we're on the Wishlist page, render the wishlist grid from DB
    const wishlistContainer = document.getElementById('wishlist-container');
    if (wishlistContainer) {
        loadWishlistFromDB();
    }
});

async function apiGetJsonSafe(url) {
    if (typeof window.apiGetJson === 'function') {
        const result = await window.apiGetJson(url);
        return result;
    }

    const response = await fetch(url);
    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }

    return { ok: response.ok, status: response.status, data, response };
}

async function apiPostJsonSafe(url, body) {
    if (typeof window.apiPostJson === 'function') {
        const result = await window.apiPostJson(url, body);
        return result;
    }

    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }

    return { ok: response.ok, status: response.status, data, response };
}

async function loadWishlistFromDB() {
    const container = document.getElementById('wishlist-container');
    if (!container) return;

    try {
        const result = await apiGetJsonSafe('/api/wishlist');
        const data = result.data;

        if (!result.ok || !data) {
            showEmptyState(container);
            return;
        }

        if (data.error) {
            console.error('[Wishlist] API error:', data.error);
            showEmptyState(container);
            return;
        }

        const locations = Array.isArray(data) ? data : (data.locations || []);
        console.log(`[Wishlist] Fetched ${locations.length} wishlisted locations`);

        if (locations.length === 0) {
            showEmptyState(container);
            return;
        }

        container.innerHTML = locations.map(createLocationCard).join('');
        if (typeof syncHeartIcons === 'function') {
            syncHeartIcons();
        }
    } catch (err) {
        console.error('[Wishlist] Failed to fetch:', err);
        showEmptyState(container);
    }
}

function showEmptyState(container) {
    if (!container) return;
    container.innerHTML = `
        <div class="empty-wishlist" style="grid-column: 1 / -1;">
            <i class="fa-regular fa-face-frown"></i>
            <h2 class="fw-bold">Your wishlist is lonely!</h2>
            <p>Start adding your favorite destinations from the explore page.</p>
            <button onclick="window.location.href='/explore'"
                    class="explore-cta-btn">
                <i class="fa-solid fa-compass me-2"></i> Explore Destinations
            </button>
        </div>`;
}

// DB-backed clearWishlist (Wishlist page)
async function clearWishlist() {
    if (!confirm('Are you sure you want to clear your entire wishlist?')) return;

    try {
        const result = await apiGetJsonSafe('/api/wishlist');
        const data = result.data;
        const locations = Array.isArray(data) ? data : (data.locations || []);

        for (const loc of locations) {
            await apiPostJsonSafe('/api/toggle-wishlist', { location_id: loc.location_id });
        }

        await loadWishlistFromDB();
    } catch (err) {
        console.error('[Wishlist] Clear failed:', err);
    }
}

function fetchWishlistFromAPI() {
    const fetchPromise = (typeof window.apiGetJson === 'function')
        ? window.apiGetJson('/api/wishlist').then(r => r.data)
        : fetch('/api/wishlist').then(res => res.json());

    fetchPromise
        .then(data => {
            const items = Array.isArray(data) ? data : (data.locations || []);

            // Transform to localStorage format if needed
            // The API returns full location objects. LocalStorage just needs IDs for syncing usually,
            // but our code stores {id, name, ...}. 
            // Let's just update the list of IDs we care about?
            // Actually, we should probably OVERWRITE localStorage with DB data to ensure sync.
            // But we need to format it correctly.
            const formatted = items.map(loc => ({
                id: String(loc.location_id), // Ensure string for comparison
                name: loc.name,
                img: loc.image_url,
                locality: loc.locality,
                category: loc.category
            }));

            localStorage.setItem('triplit_data', JSON.stringify(formatted));
            syncHeartIcons(); // Re-sync UI with new data
        })
        .catch(err => console.warn('[Wishlist] Failed to sync with DB:', err));
}

/**
 *  Toggle a location in the wishlist.
 *  Called from the heart button onclick on every card.
 */
function toggleWishlist(event, button) {
    event.preventDefault();
    event.stopPropagation();

    const card = button.closest('.category-card');
    const locationId = card.getAttribute('data-id');

    // Extract data from the card attributes for localStorage
    const itemData = {
        id: locationId,
        name: card.getAttribute('data-name'),
        img: card.getAttribute('data-img'),
        locality: card.getAttribute('data-locality'),
        category: card.getAttribute('data-category')
    };

    // ── 1. Update localStorage (instant, offline-friendly) ──
    let wishlist = JSON.parse(localStorage.getItem('triplit_data')) || [];
    const isAlreadySaved = wishlist.some(item => item.id === itemData.id);

    if (isAlreadySaved) {
        wishlist = wishlist.filter(item => item.id !== itemData.id);
        button.querySelector('i').classList.replace('fa-solid', 'fa-regular');
        button.classList.remove('active');
    } else {
        wishlist.push(itemData);
        button.querySelector('i').classList.replace('fa-regular', 'fa-solid');
        button.classList.add('active');
    }

    localStorage.setItem('triplit_data', JSON.stringify(wishlist));
    updateWishlistCount();

    // ── 2. Also persist to DB via API ──
    if (locationId) {
        const payload = { location_id: parseInt(locationId) };

        const togglePromise = (typeof window.apiPostJson === 'function')
            ? window.apiPostJson('/api/toggle-wishlist', payload).then(r => r.data)
            : fetch('/api/toggle-wishlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(res => res.json());

        togglePromise
            .then(data => {
                console.log('[Wishlist] DB toggle:', data);

                // ─── BUG FIX #1: Sync ALL heart buttons with this location ID ───
                // This ensures that if the same location appears on multiple pages
                // (home, explore, wishlist, etc.), ALL heart icons stay in sync
                syncHeartIconsGlobally(locationId);

                // If on wishlist page and we just removed an item, delete the card
                if (window.location.pathname === '/wishlist' && isAlreadySaved) {
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.9)';
                    card.style.transition = 'all 0.3s ease';

                    setTimeout(() => {
                        card.remove();

                        // Check if wishlist is now empty
                        const container = document.getElementById('wishlist-container');
                        if (container && container.querySelectorAll('.category-card').length === 0) {
                            if (typeof showEmptyState === 'function') {
                                showEmptyState(container);
                            }
                        }
                    }, 300);
                }
            })
            .catch(err => console.warn('[Wishlist] DB toggle failed (offline?):', err));
    }
}

/**
 *  Sync heart icons to match localStorage state.
 *  Called after cards are rendered on any page.
 */
function syncHeartIcons() {
    const wishlist = JSON.parse(localStorage.getItem('triplit_data')) || [];
    const allCards = document.querySelectorAll('.category-card');

    allCards.forEach(card => {
        const cardId = card.getAttribute('data-id');
        const button = card.querySelector('.wishlist-btn');
        if (!button) return;

        const isSaved = wishlist.some(item => String(item.id) === String(cardId));
        const icon = button.querySelector('i');

        if (isSaved) {
            icon.classList.replace('fa-regular', 'fa-solid');
            button.classList.add('active');
        } else {
            icon.classList.replace('fa-solid', 'fa-regular');
            button.classList.remove('active');
        }
    });
}

/**
 *  BUG FIX #1: Sync ALL heart buttons with a specific location ID.
 *  This is called after a successful DB wishlist toggle to ensure
 *  ALL instances of a location card (across different pages/sections)
 *  stay in sync visually.
 *  @param {string|number} locationId - The location ID to sync
 */
function syncHeartIconsGlobally(locationId) {
    const wishlist = JSON.parse(localStorage.getItem('triplit_data')) || [];

    // Find ALL buttons with this location ID
    const allButtonsWithThisId = document.querySelectorAll(`.category-card[data-id="${locationId}"] .wishlist-btn`);

    // Check if this location is in the wishlist
    const isSaved = wishlist.some(item => String(item.id) === String(locationId));

    // Update each button
    allButtonsWithThisId.forEach(button => {
        const icon = button.querySelector('i');

        if (isSaved) {
            // Location is wishlisted → show solid red heart
            icon.classList.remove('fa-regular');
            icon.classList.add('fa-solid');
            button.classList.add('active');
        } else {
            // Location is not wishlisted → show outline heart
            icon.classList.remove('fa-solid');
            icon.classList.add('fa-regular');
            button.classList.remove('active');
        }
    });

    console.log(`[Wishlist] Synced ${allButtonsWithThisId.length} heart button(s) for location ID: ${locationId}`);
}

/**
 *  Remove a single item from the wishlist (used on the Wishlist page).
 */
function removeFromWishlist(id) {
    // Remove from localStorage
    let wishlist = JSON.parse(localStorage.getItem('triplit_data')) || [];
    wishlist = wishlist.filter(item => item.id !== id);
    localStorage.setItem('triplit_data', JSON.stringify(wishlist));

    // Remove from DB
    const payload = { location_id: parseInt(id) };
    if (typeof window.apiPostJson === 'function') {
        window.apiPostJson('/api/toggle-wishlist', payload)
            .catch(err => console.warn('[Wishlist] Remove failed:', err));
    } else {
        fetch('/api/toggle-wishlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).catch(err => console.warn('[Wishlist] Remove failed:', err));
    }

    // Re-render if on wishlist page
    if (typeof loadWishlistFromDB === 'function') {
        loadWishlistFromDB();
    }
    syncHeartIcons();
}

/**
 *  Update the navbar wishlist count badge.
 */
function updateWishlistCount() {
    const countBadge = document.getElementById('wishlist-count');
    if (!countBadge) return;

    const wishlist = JSON.parse(localStorage.getItem('triplit_data')) || [];
    countBadge.innerText = wishlist.length;
    countBadge.style.display = wishlist.length > 0 ? 'block' : 'none';
}