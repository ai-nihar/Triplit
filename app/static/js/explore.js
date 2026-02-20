/**
 * ===================================================================
 *  Explore Page — Server-Side Paginated Location Cards
 * ===================================================================
 *
 *  DEPENDS ON: location-card.js (shared createLocationCard function)
 *
 *  DATA FLOW:
 *    1.  Page loads → fetch('/api/explore-locations?page=1&limit=40')
 *    2.  API returns: { locations: [...], page, limit, total, total_pages }
 *    3.  JS renders cards using shared createLocationCard()
 *    4.  Pagination is SERVER-SIDE (each page click fetches new data)
 *    5.  Search & filter still operate client-side on current page data
 * ===================================================================
 */

// ──────────────────────────────────────────────
//  STATE
// ──────────────────────────────────────────────
let allLocations = [];   // Current page's locations from API
let currentPage = 1;
let totalPages = 1;
let totalItems = 0;
const ITEMS_PER_PAGE = 40;  // 4 columns × 10 rows

// ──────────────────────────────────────────────
//  RENDER: Inject cards into grid
// ──────────────────────────────────────────────
function renderLocations(locations) {
    const grid = document.getElementById('cards-grid');

    // Remove any loading spinner
    const loader = document.getElementById('locations-loading');
    if (loader) loader.remove();

    if (!locations || locations.length === 0) {
        grid.innerHTML = `
            <div class="col-12 text-center py-5" style="grid-column: 1 / -1;">
                <i class="fa-solid fa-map-location-dot" style="font-size:2.5rem;color:#ccc;"></i>
                <p class="text-muted mt-3">No locations available at the moment.</p>
            </div>`;
        return;
    }

    // Use the SHARED createLocationCard() from location-card.js
    grid.innerHTML = locations.map(createLocationCard).join('');

    // Sync wishlist hearts
    if (typeof syncHeartIcons === 'function') {
        syncHeartIcons();
    }

    console.log(`[Explore] Rendered ${locations.length} location cards (page ${currentPage}/${totalPages})`);
}

// ──────────────────────────────────────────────
//  FETCH: Load paginated locations from API
// ──────────────────────────────────────────────
async function fetchLocations(page = 1) {
    const grid = document.getElementById('cards-grid');

    // Show loading state
    grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 60px 0;">
            <div class="spinner-border text-secondary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="text-muted mt-2">Loading destinations...</p>
        </div>`;

    try {
        const url = `/api/explore-locations?page=${page}&limit=${ITEMS_PER_PAGE}`;
        let ok;
        let status;
        let data;

        if (typeof window.apiGetJson === 'function') {
            const result = await window.apiGetJson(url);
            ok = result.ok;
            status = result.status;
            data = result.data;
        } else {
            const response = await fetch(url);
            ok = response.ok;
            status = response.status;
            data = await response.json();
        }

        if (!ok) {
            throw new Error(`Server responded with ${status}`);
        }

        if (data.error) {
            console.error('[Explore] API Error:', data.error);
            renderLocations([]);
            return;
        }

        // Update state from paginated response
        allLocations = data.locations;
        currentPage = data.page;
        totalPages = data.total_pages;
        totalItems = data.total;

        console.log(`[Explore] Fetched page ${currentPage}/${totalPages} (${allLocations.length} items, ${totalItems} total)`);

        renderLocations(allLocations);
        updatePaginationUI();

        // Scroll to top of grid
        const container = document.querySelector('.explore-grid-container');
        if (container && page > 1) {
            container.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

    } catch (err) {
        console.error('[Explore] Failed to fetch locations:', err);
        renderLocations([]);
    }
}

// ──────────────────────────────────────────────
//  SEARCH — filter client-side on current page
// ──────────────────────────────────────────────
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function triggerSearch() {
    const input = document.getElementById('destinationSearch');
    const raw = input ? (input.value || '').trim() : '';
    const query = raw;

    if (!query) {
        renderLocations(allLocations);
        updatePaginationUI();
        return;
    }

    const grid = document.getElementById('cards-grid');
    grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 60px 0;">
            <div class="spinner-border text-secondary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="text-muted mt-2">Searching for "${escapeHtml(query)}"...</p>
        </div>`;

    try {
        const url = `/api/locations/search?q=${encodeURIComponent(query)}`;
        let ok;
        let status;
        let data;

        if (typeof window.apiGetJson === 'function') {
            const result = await window.apiGetJson(url);
            ok = result.ok;
            status = result.status;
            data = result.data;
        } else {
            const response = await fetch(url);
            ok = response.ok;
            status = response.status;
            data = await response.json();
        }

        if (!ok) {
            throw new Error(`Server responded with ${status}`);
        }

        const locations = (data && data.locations) || [];
        if (!locations.length) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5" style="grid-column: 1 / -1;">
                    <i class="fa-solid fa-magnifying-glass" style="font-size:2.2rem;color:#ccc;"></i>
                    <p class="text-muted mt-3">No results for "${escapeHtml(query)}"</p>
                </div>`;
            document.getElementById('pagination-container').style.display = 'none';
            return;
        }

        renderLocations(locations);
        document.getElementById('pagination-container').style.display = 'none';

    } catch (err) {
        console.error('[Explore] Search failed:', err);
        renderLocations([]);
        document.getElementById('pagination-container').style.display = 'none';
    }
}

// ──────────────────────────────────────────────
//  REGION FILTER — populate from DB
// ──────────────────────────────────────────────
(async function loadRegionFilter() {
    try {
        let data;
        if (typeof window.apiGetJson === 'function') {
            const result = await window.apiGetJson('/api/regions/all');
            if (!result.ok) return;
            data = result.data;
        } else {
            const res = await fetch('/api/regions/all');
            if (!res.ok) return;
            data = await res.json();
        }
        const select = document.getElementById('regionFilter');
        if (!select) return;
        (data.regions || []).forEach(region => {
            const opt = document.createElement('option');
            opt.value = region;
            opt.textContent = region;
            select.appendChild(opt);
        });
        console.log(`[Explore] Loaded ${(data.regions || []).length} regions into filter dropdown`);
    } catch (err) {
        console.error('[Explore] Failed to load regions:', err);
    }
})();

// ──────────────────────────────────────────────
//  CATEGORY FILTER — populate from DB
// ──────────────────────────────────────────────
(async function loadCategoryFilter() {
    try {
        let data;
        if (typeof window.apiGetJson === 'function') {
            const result = await window.apiGetJson('/api/categories/all');
            if (!result.ok) return;
            data = result.data;
        } else {
            const res = await fetch('/api/categories/all');
            if (!res.ok) return;
            data = await res.json();
        }
        const select = document.getElementById('categoryFilter');
        if (!select) return;
        // Clear existing hardcoded options (keep the first "Category" placeholder)
        select.innerHTML = '<option value="all">Category</option>';
        (data.categories || []).forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
            select.appendChild(opt);
        });
        console.log(`[Explore] Loaded ${(data.categories || []).length} categories into filter dropdown`);
    } catch (err) {
        console.error('[Explore] Failed to load categories:', err);
    }
})();

// ──────────────────────────────────────────────
//  FILTERS — Category & Region dropdowns
// ──────────────────────────────────────────────
function applyFilters() {
    const selectedCategory = document.getElementById('categoryFilter').value;
    const selectedRegion = document.getElementById('regionFilter').value;

    // If both filters are "all", restore full view with pagination
    if (selectedCategory === 'all' && selectedRegion === 'all') {
        renderLocations(allLocations);
        updatePaginationUI();
        return;
    }

    const matched = allLocations.filter(loc => {
        const catMatch = selectedCategory === 'all' || (loc.category || '').toLowerCase() === selectedCategory.toLowerCase();
        const regMatch = selectedRegion === 'all' || (loc.region || '').toLowerCase() === selectedRegion.toLowerCase();
        return catMatch && regMatch;
    });

    renderLocations(matched);
    document.getElementById('pagination-container').style.display = 'none';
}

// ──────────────────────────────────────────────
//  PAGINATION UI — Premium themed
// ──────────────────────────────────────────────
function updatePaginationUI() {
    const container = document.getElementById('pagination-container');
    const numbersEl = document.getElementById('pagination-numbers');

    if (totalPages <= 1) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'flex';
    numbersEl.innerHTML = '';

    // Update prev/next arrow states
    const prevBtn = container.querySelector('.pagination-btn:first-child');
    const nextBtn = container.querySelector('.pagination-btn:last-child');
    if (prevBtn) prevBtn.disabled = currentPage === 1;
    if (nextBtn) nextBtn.disabled = currentPage === totalPages;

    // Smart page range (show max 7 page buttons)
    const maxVisible = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage < maxVisible - 1) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    // First page + ellipsis
    if (startPage > 1) {
        addPageBtn(numbersEl, 1);
        if (startPage > 2) addEllipsis(numbersEl);
    }

    // Page number buttons
    for (let i = startPage; i <= endPage; i++) {
        addPageBtn(numbersEl, i);
    }

    // Ellipsis + last page
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) addEllipsis(numbersEl);
        addPageBtn(numbersEl, totalPages);
    }

    // Page info text
    let infoEl = document.getElementById('pagination-info');
    if (!infoEl) {
        infoEl = document.createElement('div');
        infoEl.id = 'pagination-info';
        infoEl.className = 'pagination-info';
        container.parentNode.insertBefore(infoEl, container.nextSibling);
    }
    infoEl.textContent = `Page ${currentPage} of ${totalPages}  ·  ${totalItems} destinations`;
}

function addPageBtn(container, num) {
    const btn = document.createElement('button');
    btn.className = `pagination-number ${num === currentPage ? 'active' : ''}`;
    btn.textContent = num;
    btn.onclick = () => goToPage(num);
    container.appendChild(btn);
}

function addEllipsis(container) {
    const span = document.createElement('span');
    span.className = 'pagination-ellipsis';
    span.textContent = '···';
    container.appendChild(span);
}

function goToPage(page) {
    if (page < 1 || page > totalPages || page === currentPage) return;
    fetchLocations(page);
}

function previousPage() {
    if (currentPage > 1) goToPage(currentPage - 1);
}

function nextPage() {
    if (currentPage < totalPages) goToPage(currentPage + 1);
}

// ──────────────────────────────────────────────
//  MODAL: Handled by location-modal.js (global)
//  openLocationDetail() is defined there.
// ──────────────────────────────────────────────

// ──────────────────────────────────────────────
//  INIT — runs on page load
// ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // 1. Fetch first page
    fetchLocations(1);

    // 2. Wire up live search on Enter key
    const searchInput = document.getElementById('destinationSearch');
    if (searchInput) {
        searchInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') triggerSearch();
        });
    }

    // 3. Handle search query from URL (e.g. coming from Home page)
    const urlParams = new URLSearchParams(window.location.search);
    const query = urlParams.get('search');
    if (query) {
        document.getElementById('destinationSearch').value = query;
        setTimeout(() => triggerSearch(), 800);
    }

    // ──────────────────────────────────────────────
    //  4. SCROLL-MERGE: Show navbar search when explore
    //     search bar scrolls out of view
    // ──────────────────────────────────────────────
    const exploreSearchBar = document.querySelector('.search-bar-container');
    const navSearch = document.getElementById('navbarSearch');
    const navInput = document.getElementById('navbarSearchInput');
    const exploreInput = document.getElementById('destinationSearch');

    if (exploreSearchBar && navSearch && navInput && exploreInput) {
        // Use IntersectionObserver for smooth detection
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach(entry => {
                    if (!entry.isIntersecting) {
                        // Explore search bar scrolled out — show navbar search
                        navSearch.classList.add('is-visible');
                        // Sync text from explore → navbar
                        if (exploreInput.value && !navInput.value) {
                            navInput.value = exploreInput.value;
                        }
                    } else {
                        // Explore search bar is back in view — hide navbar search
                        navSearch.classList.remove('is-visible');
                        // Sync text from navbar → explore
                        if (navInput.value && !exploreInput.value) {
                            exploreInput.value = navInput.value;
                        }
                    }
                });
            },
            { threshold: 0, rootMargin: '-80px 0px 0px 0px' }  // offset for fixed navbar height
        );
        observer.observe(exploreSearchBar);

        // Keep search text synced between both inputs
        exploreInput.addEventListener('input', () => {
            navInput.value = exploreInput.value;
        });
        navInput.addEventListener('input', () => {
            exploreInput.value = navInput.value;
        });
    }
});