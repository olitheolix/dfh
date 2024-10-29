import base64
import json
import logging
from typing import Annotated

import google.oauth2.credentials
import googleapiclient.discovery
import httplib2
import httpx
import itsdangerous
import pydantic
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from googleapiclient.errors import HttpError

import dfh.api
import dfh.watch
from dfh.models import GoogleToken, UserMe, UserToken

# Request a token to query the user's email.
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

router = APIRouter()
logit = logging.getLogger("app")


def is_authenticated(request: Request) -> str:
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


def fetch_user_email(credentials: google.oauth2.credentials.Credentials) -> str:
    """Return the Google email associated with the `credentials`."""
    disable_ssl_validation = dfh.api.isLocalDev()
    htbuild = httplib2.Http(disable_ssl_certificate_validation=disable_ssl_validation)
    client = googleapiclient.discovery.google_auth_httplib2.AuthorizedHttp(
        credentials, http=htbuild
    )

    try:
        user_info_service = googleapiclient.discovery.build("oauth2", "v2", http=client)
        user_info = user_info_service.userinfo().get().execute()
        return user_info["email"]
    except HttpError as e:
        logit.error(
            "unable to fetch user email from Google",
            {"code": e.status_code, "reason": e.reason, "detail": e.error_details},
        )
        return ""


@router.post("/validate-google-bearer-token")
async def google_auth_bearer(data: GoogleToken, request: Request, response: Response):
    """Query user info from Google and mark the user as logged in."""
    # Official Google endpoint to query user information.
    url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={data.token}"
    resp = await httpx.AsyncClient().get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=403, detail="Invalid ID token")

    email = resp.json()["email"]
    request.session["email"] = email
    response.set_cookie(key="email", value=email)


@router.get("/revoke")
async def revoke(request: Request):
    """Revoke the Google token and clear the session data.

    NOTE: This code is verbatim from
    https://developers.google.com/identity/protocols/oauth2/web-server#example
    with trivial changes to adapt it from Flask to FastAPI.

    """
    if "credentials" not in request.session:
        return HTMLResponse(
            'You need to <a href="/demo/api/auth/google-login">authorize</a> before '
            + "testing the code to revoke credentials."
        )

    # Revoke the Google credentials.
    credentials = google.oauth2.credentials.Credentials(
        **request.session["credentials"]
    )
    resp = await httpx.AsyncClient().post(
        "https://oauth2.googleapis.com/revoke",
        params={"token": credentials.token},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    # Revoke the user session.
    request.session.pop("credentials", None)

    if resp.status_code == 200:
        return "Credentials successfully revoked."
    else:
        return "Could not revoke credentials."


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
