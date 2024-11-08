import base64
import logging
from typing import Annotated

import itsdangerous
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
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
