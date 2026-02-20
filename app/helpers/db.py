import mysql.connector
from flask import g, current_app


def get_db():
    """Get a MySQL database connection for the current request.
    Connection is stored on Flask's `g` object so it's reused within a request.
    """
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host=current_app.config['DB_HOST'],
            port=current_app.config['DB_PORT'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME']
        )
    return g.db


def close_db(e=None):
    """Close the database connection at end of request."""
    db = g.pop('db', None)
    if db is not None and db.is_connected():
        db.close()


def query_db(query, args=(), one=False):
    """Execute a SELECT query and return results as list of dicts.

    Args:
        query: SQL query string with %s placeholders
        args: tuple of parameters
        one: if True, return only the first result (or None)

    Returns:
        list of dicts, or a single dict if one=True
    """
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(query, args)
    results = cursor.fetchall()
    cursor.close()

    if one:
        return results[0] if results else None
    return results


def execute_db(query, args=()):
    """Execute an INSERT/UPDATE/DELETE query.

    Args:
        query: SQL query string with %s placeholders
        args: tuple of parameters

    Returns:
        lastrowid for INSERT, or rowcount for UPDATE/DELETE
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, args)
    db.commit()
    lastrowid = cursor.lastrowid
    rowcount = cursor.rowcount
    cursor.close()

    return lastrowid if lastrowid else rowcount
