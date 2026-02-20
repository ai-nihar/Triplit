/* ==========================================================================
   PROFILE.JS — Profile Page Interactivity
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {

    // ------------------------------------------------------------------
    // 1. CHANGE PASSWORD — Button click handler
    // ------------------------------------------------------------------
    const changeBtn = document.getElementById('btn-change-password');
    if (changeBtn) {
        changeBtn.addEventListener('click', () => {
            console.log('[Profile] "Change" password clicked');

            // ============================================================
            // TODO: Implement password change flow.
            //
            // Option A — Open a modal with current/new password fields:
            //     openPasswordModal();
            //
            // Option B — Redirect to a dedicated password reset page:
            //     window.location.href = '/change-password';
            //
            // Option C — Inline expand a form below the password row:
            //     togglePasswordForm();
            // ============================================================

            alert('Password change feature coming soon!');
        });
    }

    // ------------------------------------------------------------------
    // 2. AVATAR EDIT — Edit badge click handler
    // ------------------------------------------------------------------
    const editBadge = document.getElementById('avatar-edit-badge');
    if (editBadge) {
        editBadge.addEventListener('click', () => {
            console.log('[Profile] Avatar edit clicked');

            // ============================================================
            // TODO: Implement avatar/profile edit flow.
            //
            // Option A — Open file picker for avatar upload:
            //     document.getElementById('avatar-upload').click();
            //
            // Option B — Navigate to an edit profile page:
            //     window.location.href = '/profile/edit';
            // ============================================================

            alert('Profile editing coming soon!');
        });
    }

    console.log('✓ profile.js loaded');
});
