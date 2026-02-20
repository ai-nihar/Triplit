// Home page behaviors (kept small and defensive)

(function () {
  function syncStickyNavbarSearchVisibility() {
    const navSearch = document.getElementById('navbarSearch');
    if (!navSearch) return;

    if (window.scrollY > 500) {
      navSearch.classList.add('is-visible');
    } else {
      navSearch.classList.remove('is-visible');
    }
  }

  async function loadFeaturedDestinations() {
    try {
      let data;
      if (typeof window.apiGetJson === 'function') {
        const result = await window.apiGetJson('/api/home-locations');
        data = result.data;
      } else {
        const response = await fetch('/api/home-locations');
        data = await response.json();
      }

      if (data && data.error) {
        console.error('[Home] API error:', data.error);
        renderLocationCards([], 'featured-grid', 'No featured destinations yet.');
        return;
      }

      const locations = (data && (data.locations || data)) || [];
      console.log(`[Home] Fetched ${locations.length} featured locations`);
      renderLocationCards(locations, 'featured-grid', 'No featured destinations yet.');

    } catch (err) {
      console.error('[Home] Failed to fetch:', err);
      renderLocationCards([], 'featured-grid', 'Could not load destinations.');
    }
  }

  window.addEventListener('scroll', syncStickyNavbarSearchVisibility);

  document.addEventListener('DOMContentLoaded', function () {
    syncStickyNavbarSearchVisibility();

    if (typeof renderLocationCards === 'function') {
      loadFeaturedDestinations();
    }
  });
})();
