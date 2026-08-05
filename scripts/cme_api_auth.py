"""Shared Cognito auth for operator scripts that call the CME API.

The production API requires a Cognito ID token on every request (see
docs/LOCKDOWN.md, "Production API auth"). Scripts import auth_headers()
or api_session() and send the token with each API call. Credentials come
from the environment:

    CME_API_USERNAME  Cognito username in the cme-analysis-users pool
    CME_API_PASSWORD  matching password

S3 presigned URLs must be fetched WITHOUT these headers -- S3 rejects
requests that carry both query-string signing and an Authorization header.
"""
import os
import time

import boto3
import requests

CLIENT_ID = os.environ.get("CME_COGNITO_CLIENT_ID", "42e444v111efsa21b6b3v09svp")
REGION = os.environ.get("CME_COGNITO_REGION", "us-east-1")

_cache = {"token": None, "expires": 0.0}


def get_id_token() -> str:
    """Return a cached Cognito ID token, authenticating on first use."""
    if _cache["token"] and time.time() < _cache["expires"]:
        return _cache["token"]
    username = os.environ.get("CME_API_USERNAME")
    password = os.environ.get("CME_API_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "CME_API_USERNAME / CME_API_PASSWORD must be set: the production "
            "API requires Cognito auth (docs/LOCKDOWN.md)."
        )
    client = boto3.client("cognito-idp", region_name=REGION)
    result = client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=CLIENT_ID,
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )["AuthenticationResult"]
    _cache["token"] = result["IdToken"]
    _cache["expires"] = time.time() + result.get("ExpiresIn", 3600) - 60
    return _cache["token"]


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {get_id_token()}"}


def api_session() -> requests.Session:
    """requests.Session that sends the bearer token on every request."""
    session = requests.Session()
    session.headers.update(auth_headers())
    return session
