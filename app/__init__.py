from flask import Flask, render_template, session, request, jsonify, redirect, url_for
from app.config import Config
from app.helpers.db import close_db, query_db, execute_db
from app.helpers.auth_utils import hash_password, check_password


def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

    def _current_user_id():
        return session.get('user_id')

    def _signin_response():
        return render_template('signin.html')

    def _require_login_or_signin():
        """Return a signin response if logged out, else None."""
        if not _current_user_id():
            return _signin_response()
        return None

    # Register teardown to close DB connection after each request
    app.teardown_appcontext(close_db)

    # ---- Context Processor: inject auth info into ALL templates ----
    @app.context_processor
    def inject_auth():
        """Make is_logged_in and current_user available in every template."""
        user_id = _current_user_id()
        if user_id:
            user = query_db(
                'SELECT user_id, full_name, email FROM users WHERE user_id = %s',
                (user_id,), one=True
            )
            return {
                'is_logged_in': True,
                'current_user': user or {'full_name': 'User'}
            }
        return {
            'is_logged_in': False,
            'current_user': None
        }

    # ---- Register Blueprints ----
    from app.routes.api import api_bp

    app.register_blueprint(api_bp)

    # ════════════════════════════════════════════════════════════════
    #  PAGE ROUTES — serve the polished frontend templates
    # ════════════════════════════════════════════════════════════════

    @app.route('/')
    def home():
        return render_template('index.html')

    @app.route('/explore')
    def explore():
        return render_template('explore.html')

    @app.route('/dashboard')
    def dashboard():
        maybe = _require_login_or_signin()
        if maybe:
            return maybe

        user_id = _current_user_id()
        all_trips = query_db(
            '''SELECT trip_id, trip_name, start_region, end_region, pace,
                      companion_type, season, planning_mode, trip_days,
                      trip_status, created_at
               FROM trips WHERE user_id = %s ORDER BY created_at DESC''',
            (user_id,)
        ) or []
        draft_trips = [t for t in all_trips if t['trip_status'] != 'finalized']
        final_trips = [t for t in all_trips if t['trip_status'] == 'finalized']
        return render_template('trips-dashboard.html', draft_trips=draft_trips, final_trips=final_trips)

    @app.route('/wishlist')
    def wishlist_page():
        return render_template('wishlist.html')

    @app.route('/trip')
    def create_trip():
        maybe = _require_login_or_signin()
        if maybe:
            return maybe
        return render_template('create-trip.html')

    @app.route('/draft_trip')
    @app.route('/draft_trip/<int:trip_id>')
    def draft_trip(trip_id=None):
        maybe = _require_login_or_signin()
        if maybe:
            return maybe
        return render_template('draft-trip.html', trip_id=trip_id or session.get('current_trip_id'))

    @app.route('/itinerary/<int:trip_id>')
    def trip_itinerary(trip_id: int):
        maybe = _require_login_or_signin()
        if maybe:
            return maybe

        user_id = _current_user_id()
        trip = query_db(
            'SELECT trip_id FROM trips WHERE trip_id = %s AND user_id = %s',
            (trip_id, user_id),
            one=True,
        )
        if not trip:
            return redirect(url_for('dashboard'))

        return render_template('trip-itinerary.html')

    @app.route('/profile')
    def profile():
        maybe = _require_login_or_signin()
        if maybe:
            return maybe
        return render_template('profile.html')

    # ════════════════════════════════════════════════════════════════
    #  AUTH ROUTES — JSON-based login/signup for the frontend
    # ════════════════════════════════════════════════════════════════

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if request.method == 'GET':
            return render_template('signin.html')

        # POST — handle AJAX login from new frontend
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400

        user = query_db(
            'SELECT user_id, full_name, password_hash FROM users WHERE email = %s',
            (email,), one=True
        )

        if not user or not check_password(password, user['password_hash']):
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

        # Set session
        session.permanent = True
        session['user_id'] = user['user_id']
        session['user_name'] = user['full_name']

        return jsonify({
            'success': True,
            'message': f'Welcome back, {user["full_name"]}!',
            'redirect': '/explore'
        })

    @app.route('/signup', methods=['GET', 'POST'])
    def signup_page():
        if request.method == 'GET':
            return render_template('signup.html')

        # POST — handle AJAX signup from new frontend
        full_name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not full_name or not email or not password:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Check dups
        existing = query_db('SELECT user_id FROM users WHERE email = %s', (email,), one=True)
        if existing:
            return jsonify({'success': False, 'message': 'An account with this email already exists'}), 409

        password_hash = hash_password(password)
        user_id = execute_db(
            'INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)',
            (full_name, email, password_hash)
        )

        # Auto-login after signup
        session.permanent = True
        session['user_id'] = user_id
        session['user_name'] = full_name

        return jsonify({
            'success': True,
            'message': 'Account created successfully!',
            'redirect': '/login'
        })

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect('/')

    return app
