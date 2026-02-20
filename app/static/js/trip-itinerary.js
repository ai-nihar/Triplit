/**
 * ===================================================================
 *  TRIP ITINERARY — Data Fetch & Render
 * ===================================================================
 *
 *  DEPENDS ON:
 *    - location-modal.js  (for openLocationDetail function)
 *    - location-card.js   (for createLocationCard function)
 *
 *  FLOW:
 *    1. Extract trip_id from URL (path /itinerary/<id> or query params)
 *    2. Fetch /api/trips/<trip_id>/itinerary
 *    3. Render structured layout: Regions → Days → Locations
 *    4. Attach event listeners to "See More" buttons
 * ===================================================================
 */

// ──────────────────────────────────────────────
//  STATE & CONFIGURATION
// ──────────────────────────────────────────────
let allLocationsData = [];  // Flattened array for modal lookup

// ──────────────────────────────────────────────
//  MAIN INITIALIZATION
// ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    initializeItinerary();
});

async function initializeItinerary() {
    const tripId = getTripIdFromUrl();

    if (!tripId) {
        showEmptyState('Trip ID not found', 'Please go back and select a trip.');
        return;
    }

    try {
        const [data, planData] = await Promise.all([
            fetchItineraryData(tripId),
            fetchRoutePlan(tripId),
        ]);

        if (!data || !data.regions || data.regions.length === 0) {
            showEmptyState(
                'No locations in itinerary',
                'Your itinerary doesn\'t have any locations yet. Add some locations to get started!'
            );
            return;
        }

        // Flatten all locations for modal lookup
        data.regions.forEach(region => {
            region.days.forEach(day => {
                day.locations.forEach(loc => {
                    allLocationsData.push(loc);
                });
            });
        });

        renderItinerary(data, planData && planData.plan ? planData.plan : null);
        attachEventListeners();
    } catch (error) {
        console.error('[Trip Itinerary] Error initializing itinerary:', error);
        showEmptyState(
            'Error loading itinerary',
            'Something went wrong. Please try again later.'
        );
    }
}

async function fetchRoutePlan(tripId) {
    const url = `/api/trips/${tripId}/route-plan`;
    let ok;
    let status;
    let data;

    if (typeof window.apiGetJson === 'function') {
        const result = await window.apiGetJson(url);
        ok = result.ok;
        status = result.status;
        data = result.data;
    } else {
        const res = await fetch(url);
        ok = res.ok;
        status = res.status;
        data = await res.json();
    }

    if (!ok) {
        if (status === 404) return { plan: null };
        return { plan: null };
    }
    return data;
}

// ──────────────────────────────────────────────
//  FETCH: Get itinerary data from API
// ──────────────────────────────────────────────
async function fetchItineraryData(tripId) {
    const url = `/api/trips/${tripId}/itinerary`;
    let ok;
    let status;
    let data;

    if (typeof window.apiGetJson === 'function') {
        const result = await window.apiGetJson(url);
        ok = result.ok;
        status = result.status;
        data = result.data;
    } else {
        const res = await fetch(url);
        ok = res.ok;
        status = res.status;
        data = await res.json();
    }

    if (!ok) {
        if (status === 404) {
            throw new Error('Trip not found');
        }
        throw new Error(`Server error: ${status}`);
    }

    return data;
}

// ──────────────────────────────────────────────
//  RENDER: Build the entire itinerary DOM
// ──────────────────────────────────────────────
function renderItinerary(data, plan) {
    const container = document.getElementById('itinerary-container');

    // Clear loading state
    container.innerHTML = '';

    // Optional: summary card (if optimization snapshot exists)
    if (plan && (plan.total_distance_km != null || plan.total_duration_min != null)) {
        const distanceKm = (typeof plan.total_distance_km === 'number') ? plan.total_distance_km : null;
        const durationMin = (typeof plan.total_duration_min === 'number') ? plan.total_duration_min : null;

        const hours = (typeof durationMin === 'number') ? Math.floor(durationMin / 60) : null;
        const mins = (typeof durationMin === 'number') ? Math.round(durationMin % 60) : null;
        const timeText = (hours != null && mins != null) ? `${hours}h ${mins}m` : '—';
        const distText = (distanceKm != null) ? `${distanceKm.toFixed(1)} km` : '—';

        container.insertAdjacentHTML('beforeend', `
            <div class="card mb-4">
                <div class="card-body">
                    <div class="d-flex flex-wrap justify-content-between align-items-center gap-3">
                        <div>
                            <h5 class="card-title mb-1">Route Summary</h5>
                            <div class="text-muted small">Optimized order saved for this trip</div>
                        </div>
                        <div class="d-flex gap-4">
                            <div>
                                <div class="text-muted small">Total Distance</div>
                                <div class="fw-semibold">${distText}</div>
                            </div>
                            <div>
                                <div class="text-muted small">Est. Time</div>
                                <div class="fw-semibold">${timeText}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);
    }

    // Render each region with nested days and locations
    data.regions.forEach((region, regionIndex) => {
        const regionHtml = createRegionSection(region, regionIndex + 1);
        container.insertAdjacentHTML('beforeend', regionHtml);
    });
}

// ──────────────────────────────────────────────
//  CREATE: Region Section
// ──────────────────────────────────────────────
function createRegionSection(region, regionNumber) {
    let stepCounter = 1;
    let daysHtml = '';

    const fmtMin = (m) => {
        if (typeof m !== 'number' || !isFinite(m)) return '—';
        const total = Math.max(0, Math.round(m));
        const h = Math.floor(total / 60);
        const min = total % 60;
        if (h <= 0) return `${min}m`;
        if (min === 0) return `${h}h`;
        return `${h}h ${min}m`;
    };

    // Iterate through days within this region
    region.days.forEach(day => {
        const travelText = fmtMin(day.travel_min);
        const visitText = fmtMin(day.visit_min);
        const totalText = fmtMin(day.total_min);
        const meta = (travelText !== '—' || visitText !== '—' || totalText !== '—')
            ? `<span class="text-muted small ms-2">• Travel ${travelText} • Visit ${visitText} • Total ${totalText}</span>`
            : '';

        const dayLocationsHtml = day.locations
            .map((loc, locIndex) => {
                const stepNum = stepCounter++;
                return createLocationCard(loc, stepNum);
            })
            .join('');

        daysHtml += `
            <div class="day-section">
                <div class="day-header">
                    <i class="fa-solid fa-calendar day-header__icon"></i>
                    <p class="day-header__text">Day ${day.day_number}${meta}</p>
                </div>
                <div class="day-locations">
                    ${dayLocationsHtml}
                </div>
            </div>
        `;
    });

    return `
        <div class="region-section">
            <div class="region-header">
                <h2 class="region-header__title">
                    <i class="fa-solid fa-location-dot region-header__icon"></i>
                    ${region.name}
                </h2>
            </div>
            ${daysHtml}
        </div>
    `;
}

// ──────────────────────────────────────────────
//  CREATE: Single Location Card with Photo
// ──────────────────────────────────────────────
function createLocationCard(location, stepNumber) {
    const imgSrc = location.image_url || getFallbackImageUrl(location.name);
    const locality = location.locality || location.region || 'Unknown';

    return `
        <div class="location-item">
            <!-- Timeline Node -->
            <div class="location-node">${stepNumber}</div>

            <!-- Location Content -->
            <div class="location-content">
                <!-- Header with Name & Locality -->
                <div class="location-header">
                    <h3 class="location-name">${escapeHtml(location.name)}</h3>
                    <p class="location-locality">
                        <i class="fa-solid fa-map-marker-alt location-locality__icon"></i>
                        ${escapeHtml(locality)}
                    </p>
                </div>

                <!-- Photo Card -->
                <div class="photo-card">
                    <img 
                        class="photo-card__image loading" 
                        src="${imgSrc}" 
                        alt="${escapeHtml(location.name)}"
                        loading="lazy"
                        onload="this.classList.remove('loading')"
                        onerror="this.src='${getFallbackImageUrl(location.name)}'; this.classList.remove('loading');"
                    />
                </div>

                <!-- See More Button -->
                <button 
                    class="see-more-button" 
                    data-location-id="${location.location_id}"
                    data-location-name="${escapeHtml(location.name)}"
                >
                    See More <i class="fa-solid fa-arrow-right"></i>
                </button>
            </div>
        </div>
    `;
}

// ──────────────────────────────────────────────
//  EVENT: Attach listeners to "See More" buttons
// ──────────────────────────────────────────────
function attachEventListeners() {
    const buttons = document.querySelectorAll('.see-more-button');

    buttons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();

            const locationId = this.dataset.locationId;
            const locationName = this.dataset.locationName;

            if (!locationId) {
                console.warn('[Trip Itinerary] Missing location ID on button');
                return;
            }

            // Make sure modal infrastructure exists
            if (typeof ensureModalExists === 'function') {
                ensureModalExists();
            }

            // Try to open modal by location name
            if (typeof openLocationDetail === 'function') {
                // First, populate allLocations array for the modal lookup
                if (typeof allLocations === 'undefined') {
                    window.allLocations = allLocationsData;
                } else if (!Array.isArray(window.allLocations)) {
                    window.allLocations = allLocationsData;
                } else {
                    // Merge to avoid duplicates
                    const existingIds = new Set(window.allLocations.map(l => l.location_id));
                    allLocationsData.forEach(loc => {
                        if (!existingIds.has(loc.location_id)) {
                            window.allLocations.push(loc);
                        }
                    });
                }

                // Open the modal
                openLocationDetail(locationName);
            } else {
                console.warn('[Trip Itinerary] openLocationDetail function not available');
            }
        });
    });

    console.log(`[Trip Itinerary] Attached event listeners to ${buttons.length} "See More" buttons`);
}

// ──────────────────────────────────────────────
//  UTILITY: Get trip ID from URL
// ──────────────────────────────────────────────
function getTripIdFromUrl() {
    // Check if trip_id is in the current URL path (e.g., /itinerary/123)
    const pathMatch = window.location.pathname.match(/\/itinerary\/(\d+)/);
    if (pathMatch) {
        return pathMatch[1];
    }

    // Fallback: check query params
    const params = new URLSearchParams(window.location.search);
    return params.get('trip_id') || null;
}

// ──────────────────────────────────────────────
//  UTILITY: Fallback image URL
// ──────────────────────────────────────────────
function getFallbackImageUrl(locationName) {
    const encoded = encodeURIComponent(locationName);
    return `https://via.placeholder.com/600x400?text=${encoded}`;
}

// ──────────────────────────────────────────────
//  UTILITY: HTML escape for data
// ──────────────────────────────────────────────
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// ──────────────────────────────────────────────
//  RENDER: Empty State
// ──────────────────────────────────────────────
function showEmptyState(title, subtitle) {
    const container = document.getElementById('itinerary-container');
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state__icon">
                <i class="fa-solid fa-map-location-dot"></i>
            </div>
            <h2 class="empty-state__title">${escapeHtml(title)}</h2>
            <p class="empty-state__subtitle">${escapeHtml(subtitle)}</p>
            <button onclick="window.location.href='/dashboard'" class="btn btn-primary rounded-pill mt-4 px-4">
                <i class="fa-solid fa-arrow-left me-2"></i> Back to Dashboard
            </button>
        </div>
    `;
}
