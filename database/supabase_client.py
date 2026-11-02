"""Supabase client module for Spendly.

Provides a singleton Supabase client instance for database operations.
All data access goes through this module to keep database logic centralized.
"""
from __future__ import annotations

import os
from typing import Optional

from supabase import create_client, Client


# Singleton client instance
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Return the Supabase client singleton.

    Creates the client on first call and reuses it for subsequent calls.
    Reads configuration from environment variables.
    """
    global _supabase_client

    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set in environment variables. "
                "Copy .env.example to .env and fill in your Supabase credentials."
            )

        _supabase_client = create_client(url, key)

    return _supabase_client


def reset_client() -> None:
    """Reset the Supabase client singleton.

    Useful for testing to ensure a fresh client for each test.
    """
    global _supabase_client
    _supabase_client = None


def get_auth_header() -> dict[str, str]:
    """Get the Authorization header with the current user's access token.

    Returns an empty dict if no user is authenticated.
    """
    from flask import session

    access_token = session.get("supabase_access_token")
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    return {}


def get_authenticated_client() -> Client:
    """Return a Supabase client with the user's access token.

    This client can perform operations on behalf of the authenticated user.
    Raises ValueError if no user is authenticated.
    """
    from flask import session

    access_token = session.get("supabase_access_token")
    if not access_token:
        raise ValueError("No authenticated user. Access token not found in session.")

    # Create a new client with the user's access token
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set.")

    client = create_client(url, key)
    client.auth.set_session(access_token)
    return client
