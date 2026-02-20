// Shared location search + autocomplete for Home / Explore / Draft / Navbar
// Uses DB-backed suggestions via /api/locations/autocomplete

(function () {
  const AUTOCOMPLETE_ENDPOINT = '/api/locations/autocomplete';
  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 250;

  function debounce(fn, wait) {
    let timer = null;
    return function debounced() {
      const ctx = this;
      const args = arguments;
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        timer = null;
        fn.apply(ctx, args);
      }, wait);
    };
  }

  async function apiGetJsonSafe(url) {
    if (typeof window.apiGetJson === 'function') {
      const result = await window.apiGetJson(url);
      return { ok: result.ok, status: result.status, data: result.data };
    }

    const res = await fetch(url);
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    return { ok: res.ok, status: res.status, data };
  }

  function findHostElement(inputEl) {
    if (!inputEl) return null;
    return (
      inputEl.closest('.search-bar-container') ||
      inputEl.closest('.search-container') ||
      inputEl.closest('.search-input-wrapper') ||
      inputEl.parentElement
    );
  }

  function formatSubtitle(loc) {
    const left = (loc.locality || '').trim();
    const right = (loc.region || '').trim();
    if (left && right) return `${left} · ${right}`;
    return left || right || '';
  }

  function attachLocationAutocomplete(inputEl, options) {
    if (!inputEl) return;

    const onSubmit = (options && options.onSubmit) || null;
    const onSelect = (options && options.onSelect) || null;
    const minChars = (options && options.minChars) || MIN_CHARS;

    const host = findHostElement(inputEl);
    if (!host) return;

    host.classList.add('loc-autocomplete-host');

    const dropdown = document.createElement('div');
    dropdown.className = 'loc-autocomplete-dropdown';
    dropdown.style.display = 'none';
    host.appendChild(dropdown);

    let items = [];
    let activeIndex = -1;
    let abortController = null;

    function hide() {
      dropdown.style.display = 'none';
      dropdown.innerHTML = '';
      items = [];
      activeIndex = -1;
    }

    function setActive(index) {
      activeIndex = index;
      const children = dropdown.querySelectorAll('.loc-autocomplete-item');
      children.forEach((el, i) => {
        if (i === activeIndex) el.classList.add('is-active');
        else el.classList.remove('is-active');
      });
    }

    function render(list) {
      items = Array.isArray(list) ? list : [];
      activeIndex = -1;

      if (!items.length) {
        hide();
        return;
      }

      dropdown.innerHTML = '';
      items.forEach((loc, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'loc-autocomplete-item';

        const title = document.createElement('div');
        title.className = 'loc-autocomplete-title';
        title.textContent = loc.name || '';

        const subtitleText = formatSubtitle(loc);
        if (subtitleText) {
          const subtitle = document.createElement('div');
          subtitle.className = 'loc-autocomplete-subtitle';
          subtitle.textContent = subtitleText;
          btn.appendChild(title);
          btn.appendChild(subtitle);
        } else {
          btn.appendChild(title);
        }

        btn.addEventListener('mousedown', function (e) {
          // Prevent blur before click selection.
          e.preventDefault();
        });

        btn.addEventListener('click', function () {
          inputEl.value = loc.name || inputEl.value;
          hide();
          if (typeof onSelect === 'function') {
            onSelect(loc);
          }
        });

        dropdown.appendChild(btn);

        // Keep dropdown from being huge
        if (idx >= 19) return;
      });

      dropdown.style.display = 'block';
    }

    const fetchSuggestions = debounce(async function () {
      const q = (inputEl.value || '').trim();
      if (!q || q.length < minChars) {
        hide();
        return;
      }

      if (abortController) {
        try {
          abortController.abort();
        } catch (e) {
          // ignore
        }
      }
      abortController = new AbortController();

      try {
        const url = `${AUTOCOMPLETE_ENDPOINT}?q=${encodeURIComponent(q)}&limit=10`;

        // apiGetJsonSafe() doesn't take AbortController. For fetch-only cancellation,
        // we do a direct fetch when api-client isn't present.
        let result;
        if (typeof window.apiGetJson === 'function') {
          result = await apiGetJsonSafe(url);
        } else {
          const res = await fetch(url, { signal: abortController.signal });
          const data = await res.json().catch(() => null);
          result = { ok: res.ok, status: res.status, data };
        }

        if (!result.ok) {
          hide();
          return;
        }

        const locations = (result.data && result.data.locations) || [];
        render(locations);
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        hide();
      }
    }, DEBOUNCE_MS);

    inputEl.addEventListener('input', fetchSuggestions);

    inputEl.addEventListener('focus', function () {
      fetchSuggestions();
    });

    inputEl.addEventListener('keydown', function (e) {
      if (dropdown.style.display !== 'block') {
        if (e.key === 'Enter' && typeof onSubmit === 'function') {
          e.preventDefault();
          onSubmit(e);
        }
        return;
      }

      if (e.key === 'Escape') {
        hide();
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = Math.min(items.length - 1, activeIndex + 1);
        setActive(next);
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = Math.max(0, activeIndex - 1);
        setActive(prev);
        return;
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        if (activeIndex >= 0 && items[activeIndex]) {
          const loc = items[activeIndex];
          inputEl.value = loc.name || inputEl.value;
          hide();
          if (typeof onSelect === 'function') onSelect(loc);
        } else if (typeof onSubmit === 'function') {
          hide();
          onSubmit(e);
        }
      }
    });

    document.addEventListener('click', function (e) {
      if (!host.contains(e.target)) hide();
    });
  }

  function navigateToExplore(query) {
    const q = (query || '').trim();
    if (!q) {
      window.location.href = '/explore';
      return;
    }
    window.location.href = `/explore?search=${encodeURIComponent(q)}`;
  }

  window.navbarSearchSubmit = function navbarSearchSubmit(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }

    const input = document.getElementById('navbarSearchInput');
    const query = input ? (input.value || '').trim() : '';

    // If already on Explore page, search inline instead of redirecting
    if (window.location.pathname === '/explore' && typeof window.triggerSearch === 'function') {
      window.triggerSearch();
      return;
    }

    navigateToExplore(query);
  };

  window.homeSearchSubmit = function homeSearchSubmit(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }

    const input = document.getElementById('homeSearchInput');
    const query = input ? (input.value || '').trim() : '';
    navigateToExplore(query);
  };

  document.addEventListener('DOMContentLoaded', function () {
    // Navbar
    const navbarInput = document.getElementById('navbarSearchInput');
    if (navbarInput) {
      attachLocationAutocomplete(navbarInput, {
        onSubmit: function (e) {
          if (typeof window.navbarSearchSubmit === 'function') {
            window.navbarSearchSubmit(e);
          } else {
            navigateToExplore(navbarInput.value);
          }
        },
        onSelect: function (loc) {
          // If on Explore page, set value and search inline
          if (window.location.pathname === '/explore' && typeof window.triggerSearch === 'function') {
            navbarInput.value = (loc && loc.name) || navbarInput.value;
            window.triggerSearch();
            return;
          }
          navigateToExplore((loc && loc.name) || navbarInput.value);
        },
      });
    }

    // Home hero
    const homeInput = document.getElementById('homeSearchInput');
    if (homeInput) {
      attachLocationAutocomplete(homeInput, {
        onSubmit: function (e) {
          window.homeSearchSubmit(e);
        },
        onSelect: function (loc) {
          navigateToExplore((loc && loc.name) || homeInput.value);
        },
      });
    }

    // Explore
    const exploreInput = document.getElementById('destinationSearch');
    if (exploreInput) {
      attachLocationAutocomplete(exploreInput, {
        onSubmit: function () {
          if (typeof window.triggerSearch === 'function') window.triggerSearch();
        },
        onSelect: function () {
          if (typeof window.triggerSearch === 'function') window.triggerSearch();
        },
      });
    }

    // Draft
    const draftInput = document.getElementById('location-search-input');
    if (draftInput) {
      attachLocationAutocomplete(draftInput, {
        onSubmit: function () {
          if (typeof window.searchLocations === 'function') window.searchLocations();
        },
        onSelect: function () {
          if (typeof window.searchLocations === 'function') window.searchLocations();
        },
      });
    }
  });
})();
