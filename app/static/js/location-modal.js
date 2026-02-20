/**
 * ===================================================================
 *  Location Detail Modal — Global Reusable Component
 * ===================================================================
 *
 *  USAGE:
 *    openLocationDetail('Gateway of India')
 *    — looks up location data from the page's allLocations array
 *    — falls back to reading data attributes from the clicked card
 *
 *  DEPENDS ON:
 *    - location-modal.css  (styles)
 *    - Font Awesome 6      (icons)
 *
 *  The modal HTML is injected once on first open via ensureModalExists().
 * ===================================================================
 */

// ──────────────────────────────────────────────
//  DESCRIPTIONS — placeholder library
// ──────────────────────────────────────────────
const locationDescriptions = {
    default: [
        `This destination is one of India's most cherished travel spots, offering a perfect blend of natural beauty, cultural depth, and unforgettable experiences. Visitors from around the world are drawn to its unique character, vibrant local life, and stunning landscapes.`,
        `Whether you're seeking peaceful moments amidst nature, diving into centuries of history, or simply exploring local cuisine and traditions, this place promises a journey that stays with you long after you leave. It's an ideal stop for any travel itinerary.`
    ]
};

// ──────────────────────────────────────────────
//  CATEGORY → ICON + QUICK INFO MAPPING
// ──────────────────────────────────────────────
const categoryMeta = {
    heritage: { icon: 'fa-landmark', hours: '9:00 AM – 5:30 PM', bestTime: 'Oct – Mar' },
    historical: { icon: 'fa-landmark', hours: '9:00 AM – 5:30 PM', bestTime: 'Oct – Mar' },
    spiritual: { icon: 'fa-place-of-worship', hours: '5:00 AM – 9:00 PM', bestTime: 'Oct – Feb' },
    beach: { icon: 'fa-umbrella-beach', hours: 'Open 24 hours', bestTime: 'Nov – Mar' },
    mountain: { icon: 'fa-mountain-sun', hours: 'Open 24 hours', bestTime: 'Apr – Jun' },
    hill_station: { icon: 'fa-mountain-sun', hours: 'Open 24 hours', bestTime: 'Mar – Jun' },
    nature: { icon: 'fa-leaf', hours: '6:00 AM – 6:00 PM', bestTime: 'Sep – Feb' },
    adventure: { icon: 'fa-person-hiking', hours: 'Varies by activity', bestTime: 'Mar – Jun' },
    wildlife: { icon: 'fa-paw', hours: '6:00 AM – 5:00 PM', bestTime: 'Nov – May' },
    destination: { icon: 'fa-location-dot', hours: 'Varies', bestTime: 'Oct – Mar' },
};

function getCategoryMeta(cat) {
    if (!cat) return categoryMeta.destination;
    return categoryMeta[cat.toLowerCase()] || categoryMeta.destination;
}

// ──────────────────────────────────────────────
//  MODAL HTML INJECTION (once)
// ──────────────────────────────────────────────
let modalInjected = false;

function ensureModalExists() {
    if (modalInjected) return;
    modalInjected = true;

    const html = `
    <div class="loc-modal-overlay" id="locModalOverlay">
        <div class="loc-modal" id="locModal">

            <!-- IMAGE BANNER -->
            <div class="loc-modal-image">
                <img id="locModalImg" src="" alt="Location" />
                <button class="loc-modal-close" id="locModalClose" title="Close">
                    <i class="fa-solid fa-xmark"></i>
                </button>
                <div class="loc-modal-dots">
                    <span class="loc-modal-dot active"></span>
                    <span class="loc-modal-dot"></span>
                    <span class="loc-modal-dot"></span>
                    <span class="loc-modal-dot"></span>
                    <span class="loc-modal-dot"></span>
                </div>
            </div>

            <!-- SCROLLABLE CONTENT -->
            <div class="loc-modal-body">
                <div class="loc-modal-header-row">
                    <h2 class="loc-modal-title" id="locModalTitle">Location Name</h2>
                    <span class="loc-modal-category" id="locModalCategory">
                        <i class="fa-solid fa-location-dot"></i>
                        <span id="locModalCategoryText">Destination</span>
                    </span>
                </div>

                <div class="loc-modal-location" id="locModalLocation">
                    <i class="fa-solid fa-location-dot"></i>
                    <span id="locModalLocationText">City, State</span>
                </div>

                <div class="loc-modal-desc" id="locModalDesc">
                    <p>Loading...</p>
                </div>

                <div class="loc-modal-info-grid">
                    <div class="loc-info-item">
                        <div class="loc-info-icon">
                            <i class="fa-regular fa-clock"></i>
                        </div>
                        <div class="loc-info-text">
                            <span class="loc-info-label">Opening Hours</span>
                            <span class="loc-info-value" id="locModalHours">9:00 AM – 5:30 PM</span>
                        </div>
                    </div>
                    <div class="loc-info-item">
                        <div class="loc-info-icon">
                            <i class="fa-regular fa-calendar"></i>
                        </div>
                        <div class="loc-info-text">
                            <span class="loc-info-label">Best Time</span>
                            <span class="loc-info-value" id="locModalBestTime">Oct – Mar</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- STICKY FOOTER -->
            <div class="loc-modal-footer">
                <button class="loc-modal-add-btn" id="locModalAddTrip">
                    <i class="fa-solid fa-plus"></i>
                    Add to Trip
                </button>
                <button class="loc-modal-heart-btn" id="locModalHeart" title="Save to Wishlist">
                    <i class="fa-regular fa-heart"></i>
                </button>
            </div>

        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);

    // ── Event Listeners ──
    const overlay = document.getElementById('locModalOverlay');
    const closeBtn = document.getElementById('locModalClose');
    const modal = document.getElementById('locModal');
    const addBtn = document.getElementById('locModalAddTrip');
    const heartBtn = document.getElementById('locModalHeart');

    // Close on X button
    closeBtn.addEventListener('click', closeLocationModal);

    // Close on overlay click (not the modal itself)
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeLocationModal();
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            closeLocationModal();
        }
    });

    // Add to Trip → open trip picker modal
    addBtn.addEventListener('click', () => {
        const title = document.getElementById('locModalTitle').textContent;
        const locationId = document.getElementById('locModalHeart').dataset.locationId;

        console.log('[Modal Add to Trip] Location:', title, 'ID:', locationId);

        if (!locationId || locationId === 'null' || locationId === 'undefined') {
            alert('Error: Location ID not found. Please try again.');
            return;
        }

        if (typeof openTripPickerForLocation === 'function') {
            openTripPickerForLocation(parseInt(locationId));
            return;
        }

        alert('Trip picker is not available on this page.');
    });

    // Heart toggle
    heartBtn.addEventListener('click', () => {
        heartBtn.classList.toggle('active');
        const icon = heartBtn.querySelector('i');
        if (heartBtn.classList.contains('active')) {
            icon.className = 'fa-solid fa-heart';
        } else {
            icon.className = 'fa-regular fa-heart';
        }

        // Trigger the real wishlist toggle if available
        const locId = heartBtn.dataset.locationId;
        if (locId && typeof toggleWishlist === 'function') {
            // Build a mock event + element to match existing toggleWishlist API
            const payload = { location_id: parseInt(locId) };

            const togglePromise = (typeof window.apiPostJson === 'function')
                ? window.apiPostJson('/api/toggle-wishlist', payload).then(r => r.data)
                : fetch('/api/toggle-wishlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).then(r => r.json());

            togglePromise
                .then(data => {
                    console.log('[Modal] Wishlist toggled:', data.action);
                })
                .catch(err => {
                    console.error('[Modal] Wishlist error:', err);
                });
        }
    });
}

// ──────────────────────────────────────────────
//  OPEN MODAL — called from "See More" links
// ──────────────────────────────────────────────
function openLocationDetail(locationName) {
    ensureModalExists();

    // Try to find location data from the page's arrays
    let loc = null;

    // Check Explore page data (and potentially Draft page data if exposed?)
    if (typeof allLocations !== 'undefined' && Array.isArray(allLocations)) {
        loc = allLocations.find(l => l.name === locationName);
    }

    // Fallback: read data from the card's data attributes
    if (!loc) {
        const safeName = locationName.replace(/"/g, '\\"');

        // Support both legacy cards (.category-card) and draft scroll cards (.loc-scroll-card)
        const card = document.querySelector(
            `.category-card[data-name="${safeName}"] , .loc-scroll-card[data-name="${safeName}"]`
        );
        if (card) {
            loc = {
                location_id: card.dataset.id,
                name: card.dataset.name,
                image_url: card.dataset.img,
                locality: card.dataset.locality,
                region: card.dataset.region,
                category: card.dataset.category,
                description: card.dataset.description
            };
        }
    }

    if (!loc) {
        console.warn('[Modal] Location not found:', locationName);
        return;
    }

    // ── Populate modal fields ──
    const meta = getCategoryMeta(loc.category);
    const catIcon = meta.icon || 'fa-location-dot';
    const catText = loc.category || 'Destination';
    const locText = loc.locality
        ? `${loc.locality}${loc.region ? ', ' + loc.region : ''}`
        : (loc.region || 'India');

    // Dynamic description support
    const descArray = loc.description
        ? [loc.description]
        : (locationDescriptions[locationName] || locationDescriptions.default);

    const imgEl = document.getElementById('locModalImg');
    if (imgEl) {
        imgEl.src = loc.image_url || '';
        imgEl.alt = loc.name;
    }
    document.getElementById('locModalTitle').textContent = loc.name;
    document.getElementById('locModalCategoryText').textContent = catText;
    document.getElementById('locModalCategory').querySelector('i').className = `fa-solid ${catIcon}`;
    document.getElementById('locModalLocationText').textContent = locText;
    document.getElementById('locModalDesc').innerHTML = descArray.map(p => `<p>${p}</p>`).join('');
    document.getElementById('locModalHours').textContent = meta.hours;
    document.getElementById('locModalBestTime').textContent = meta.bestTime;

    // Set heart state
    const heartBtn = document.getElementById('locModalHeart');
    heartBtn.dataset.locationId = loc.location_id || '';

    // Check if already wishlisted (look for active heart on the card)
    // Use escaping for selector
    const cardSelector = `.category-card[data-name="${locationName.replace(/"/g, '\\"')}"] .wishlist-btn.active`;
    const card = document.querySelector(cardSelector);

    if (card) {
        heartBtn.classList.add('active');
        heartBtn.querySelector('i').className = 'fa-solid fa-heart';
    } else {
        heartBtn.classList.remove('active');
        heartBtn.querySelector('i').className = 'fa-regular fa-heart';
    }

    // ── Show modal ──
    const overlay = document.getElementById('locModalOverlay');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden'; // Prevent background scroll

    // Scroll content to top
    const bodyEl = document.querySelector('.loc-modal-body');
    if (bodyEl) bodyEl.scrollTop = 0;

    console.log(`[Modal] Opened: ${loc.name}`);
}

// ──────────────────────────────────────────────
//  CLOSE MODAL
// ──────────────────────────────────────────────
function closeLocationModal() {
    const overlay = document.getElementById('locModalOverlay');
    if (!overlay) return;

    overlay.classList.remove('active');
    document.body.style.overflow = ''; // Restore scrolling
}
