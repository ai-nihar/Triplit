from functools import wraps
import hashlib
import os

from flask import session, redirect, url_for, flash, request, jsonify


def hash_password(password):
    """Hash a password using SHA-256 with a random salt.

    Returns:
        str: salt$hash format string
    """
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def check_password(password, stored_hash):
    """Verify a password against a stored salt$hash string.

    Args:
        password: plain text password to verify
        stored_hash: salt$hash string from database

    Returns:
        bool: True if password matches
    """
    salt, hashed = stored_hash.split('$')
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


def login_required(f):
    """Decorator to protect routes that require authentication.
    Redirects to login page if user is not logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # For API endpoints, return JSON so frontend fetch() can handle it.
            if request.path.startswith('/api') or request.blueprint == 'api':
                return jsonify({'error': 'Unauthorized'}), 401

            flash('Please log in to access this feature.', 'warning')
            return redirect(url_for('login_page', next=request.path))
        return f(*args, **kwargs)
    return decorated_function
