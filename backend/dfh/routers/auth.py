import os
import base64
import logging
from typing import Annotated

import itsdangerous
from fastapi import (
    APIRouter, Depends, HTTPException, Request, Response, status,
)

from dfh.models import GoogleToken, ServerConfig, UserMe, UserToken
from dfh.routers.dependencies import can_login, is_authenticated

from .dependencies import d_db
from .shared import get_config

# Request a token to query the user's email.
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

router = APIRouter()
logit = logging.getLogger("app")


@router.post("/validate-google-bearer-token")
async def google_auth_bearer(
    data: GoogleToken,
    cfg: Annotated[ServerConfig, Depends(get_config)],
    request: Request,
    response: Response,
    db: d_db,
):
    """Query user info from Google and mark the user as logged in."""
    # Official Google endpoint to query user information.
    url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={data.token}"
    resp = await cfg.httpclient.get(url)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token"
        )
    email = resp.json()["email"]

    # Verify the user is allowed to login.
    can_login(db, email)

    request.session["email"] = email
    response.set_cookie(key="email", value=email)


# fixme: good idea but will not work if replicated across pods. Need to replace
# it with a database lookup.
seen_codes = set()

@router.post("/validate-github-token")
async def validate_github_token(
    data: GoogleToken,
    cfg: Annotated[ServerConfig, Depends(get_config)],
    request: Request,
    response: Response,
):
    """Exchange the authorization code for an access token."""
    if data.code in seen_codes:
        return
    seen_codes.add(data.code)

    # fixme: remove hard coded.
    CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
    CLIENT_ID = "Ov23liYTV9HqYxBfVqcy"

    url = "https://github.com/login/oauth/access_token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": data.code,
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    resp = await cfg.httpclient.post(url, json=payload, headers=headers)
    body = resp.json()
    resp.raise_for_status()

    # fixme: raise proper HTTP exception
    if "access_token" not in body:
        raise Exception("Failed to retrieve access token: " + str(body))

    email = get_user_info(body["access_token"])
    request.session["email"] = email
    response.set_cookie(key="email", value=email)

    logit.info(f"succesfully authenticated user {email}")

# fixme: function is a hack currently.
def get_user_info(access_token):
    """Query GitHub API for user information."""
    url = "https://api.github.com/user"
    headers = {"Authorization": f"Bearer {access_token}"}

    import httpx
    response = httpx.get(url, headers=headers)
    response.raise_for_status()  # Raise an error for HTTP issues
    print("*** email: ", response.json())
    return response.json()["login"]


@router.get("/clear-session")
def clear_session_credentials(request: Request, response: Response):
    """Clear the browser session."""
    request.session.pop("credentials", None)
    request.session.pop("email", None)
    response.delete_cookie("email")
    return "Credentials have been cleared.<br><br>"


@router.get("/users/me", dependencies=[Depends(is_authenticated)])
def get_user_me(email: Annotated[str, Depends(is_authenticated)]) -> UserMe:
    """Return user name."""
    return UserMe(email=email)


def mint_token(email: str, key: str) -> UserToken:
    """Return a timestamped API token."""
    data = UserToken(email=email, token="")
    serializer = itsdangerous.TimestampSigner(key)
    token = serializer.sign(base64.b64encode(data.model_dump_json().encode())).decode()
    data.token = token
    return data


@router.get("/users/token", dependencies=[Depends(is_authenticated)])
def get_user_token(
    request: Request, email: Annotated[str, Depends(is_authenticated)]
) -> UserToken:
    """Return API token."""
    return mint_token(email, request.app.extra["api-token-key"])
