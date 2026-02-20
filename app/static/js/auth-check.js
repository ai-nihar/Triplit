/**
 * Authentication Check Utility
 * Handles login requirement checks for specific user actions
 * 
 * Usage: Attach to buttons/links that require authentication
 * <button onclick="requireLogin(event, '/some/action')">Action</button>
 */

// Global variable - set by Jinja2 template in navbar.html
// window.is_logged_in will be true or false
const isUserLoggedIn = window.is_logged_in === true; // Explicit boolean check

/**
 * Check if user is logged in and redirect to login if not
 * @param {Event} event - The click event
 * @param {String} actionUrl - The intended action URL (optional, used for ?next parameter)
 * @returns {Boolean} true if logged in, false if not logged in
 */
function requireLogin(event, actionUrl = null) {
    if (!isUserLoggedIn) {
        // Prevent default action and stop propagation
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        // Determine the next URL
        const nextUrl = actionUrl || window.location.pathname + window.location.search;
        
        // Redirect to login with next parameter
        window.location.href = `/login?next=${encodeURIComponent(nextUrl)}`;
        
        return false;
    }
    
    // User is logged in, allow action to proceed
    return true;
}

/**
 * Wrap an onclick handler to check authentication first
 * @param {Function} handler - The original onclick handler
 * @param {String} actionUrl - The intended action URL for redirect
 * @returns {Function} Wrapped handler function
 */
function withAuthCheck(handler, actionUrl = null) {
    return function(event, ...args) {
        if (!isUserLoggedIn) {
            event.preventDefault();
            event.stopPropagation();
            const nextUrl = actionUrl || window.location.pathname + window.location.search;
            window.location.href = `/login?next=${encodeURIComponent(nextUrl)}`;
            return false;
        }
        // User is logged in, call the original handler
        return handler.call(this, event, ...args);
    };
}

/**
 * Attach auth checks to specific UI elements on page load
 * This runs automatically when the page loads
 */
function attachAuthChecks() {
    // 1. Navbar "Trips" link
    const tripsLink = document.getElementById('trips-link');
    if (tripsLink) {
        tripsLink.addEventListener('click', function(e) {
            if (!isUserLoggedIn) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = `/login?next=${encodeURIComponent('/trip')}`;
            }
        });
    }
    
    // 2. Search bar button (if it exists)
    const searchBtn = document.querySelector('.search-btn');
    if (searchBtn) {
        searchBtn.addEventListener('click', function(e) {
            if (!isUserLoggedIn) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = `/login?next=${encodeURIComponent('/explore')}`;
            }
        });
    }
    
    // 3. Use event delegation for dynamically created card buttons
    document.addEventListener('click', function(e) {
        // Wishlist/Like button - requires login
        if (e.target.closest('.wishlist-btn')) {
            if (!isUserLoggedIn) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = `/login?next=${encodeURIComponent('/explore')}`;
                return false;
            }
        }
        
        // Add Trip button - requires login
        if (e.target.closest('.add-trip-btn')) {
            if (!isUserLoggedIn) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = `/login?next=${encodeURIComponent('/explore')}`;
                return false;
            }
        }
        
        // "See more" carousel link - requires login
        if (e.target.closest('.see-more-link')) {
            if (!isUserLoggedIn) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = `/login?next=${encodeURIComponent('/explore')}`;
                return false;
            }
        }
    }, true); // Use capture phase to intercept before other handlers
}

// Run auth checks when DOM is ready
document.addEventListener('DOMContentLoaded', attachAuthChecks);

// Also export the functions for manual use
window.requireLogin = requireLogin;
window.withAuthCheck = withAuthCheck;
window.isUserLoggedIn = isUserLoggedIn;

