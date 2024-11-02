import base64
import json
import logging
from typing import Annotated

import google.oauth2.credentials
import itsdangerous
import pydantic
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from dfh.models import GoogleToken, ServerConfig, UserMe, UserToken

from .shared import get_config

# Request a token to query the user's email.
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

router = APIRouter()
logit = logging.getLogger("app")


def is_authenticated(request: Request) -> str:
    """FastAPI dependency: return authenticated user or throw error."""
    # If the (transparently decrypted) session contains an email the user is authenticated.
    email = request.session.get("email", "")
    if email != "":
        return email

    # Decrypt the bearer token header and see if it contains valid information.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer"):
        token = auth_header.partition("Bearer ")[2]
        serializer = itsdangerous.TimestampSigner(request.app.extra["api-token-key"])

        try:
            unsigned = base64.b64decode(serializer.unsign(token, max_age=3600))
            user = UserToken.model_validate(json.loads(unsigned.decode()))
            return user.email
        except (itsdangerous.BadTimeSignature, pydantic.ValidationError):
            logit.warning("invalid or expired token")

    raise HTTPException(status_code=403, detail="not logged in")


@router.post("/validate-google-bearer-token")
async def google_auth_bearer(
    data: GoogleToken,
    cfg: Annotated[ServerConfig, Depends(get_config)],
    request: Request,
    response: Response,
):
    """Query user info from Google and mark the user as logged in."""
    # Official Google endpoint to query user information.
    url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={data.token}"
    resp = await cfg.httpclient.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=403, detail="Invalid ID token")

    email = resp.json()["email"]
    request.session["email"] = email
    response.set_cookie(key="email", value=email)


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
