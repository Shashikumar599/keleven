"""Database connections.

Two roles (see db/migrations/002_app_role.sql):
    admin  office_admin, for loading data, chunking and embedding (writes)
    app    office_app, read-only, for retrieval and the app

Each role uses its own URL if set (DATABASE_URL / APP_DATABASE_URL, e.g. when hosted), otherwise the .env values
on localhost:5433. Passing the password as a separate parameter avoids URL-encoding it.
"""
import os

import psycopg

ROLES = {
    "admin": ("DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD"),
    "app": ("APP_DATABASE_URL", None, "APP_DB_PASSWORD"),
}


def connect(role="admin"):
    url_var, user_var, password_var = ROLES[role]
    if os.environ.get(url_var):
        return psycopg.connect(os.environ[url_var])
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        user=os.environ[user_var] if user_var else "office_app",
        password=os.environ[password_var],
        dbname=os.environ["POSTGRES_DB"],
    )
