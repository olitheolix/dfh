import base64
import json
import logging
from typing import Annotated, cast

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import httplib2
import httpx
import itsdangerous
import pydantic
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from googleapiclient.errors import HttpError

import dfh.api
import dfh.watch
from dfh.models import GoogleToken, ServerConfig, UserMe, UserToken

# Request a token to query the user's email.
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

router = APIRouter()
logit = logging.getLogger("app")


def credentials_to_dict(credentials: google.oauth2.credentials.Credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def print_index_table():
    return (
        "<table>"
        + '<tr><td><a href="/demo/api/auth/test-google-api-request">Test an API request</a></td>'
        + "<td>Submit an API request and see a formatted JSON response. "
        + "    Go through the authorization flow if there are no stored "
        + "    credentials for the user.</td></tr>"
        + '<tr><td><a href="/demo/api/auth/google-login">Test the auth flow directly</a></td>'
        + "<td>Go directly to the authorization flow. If there are stored "
        + "    credentials, you still might not be prompted to reauthorize "
        + "    the application.</td></tr>"
        + '<tr><td><a href="/demo/api/auth/revoke">Revoke current credentials</a></td>'
        + "<td>Revoke the access token associated with the current user "
        + "    session. After revoking credentials, if you go to the test "
        + "    page, you should see an <code>invalid_grant</code> error."
        + "</td></tr>"
        + '<tr><td><a href="/demo/api/auth/clear-session">Clear session credentials</a></td>'
        + "<td>Clear the access token currently stored in the user session. "
        + '    After clearing the token, if you <a href="/demo/api/auth/test-google-api-request">test the '
        + "    API request</a> again, you should go back to the auth flow."
        + "</td></tr>"
        + '<tr><td><a href="/demo/api/auth/authinfo">Debug Session Info</a></td></tr>'
        + "</table>"
    )


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


@router.get("/test-google-api-request", dependencies=[Depends(is_authenticated)])
def test_api_request(request: Request):
    """Use the OAuth credentials to fetch the user email.

    This endpoint exists purely for manual testing.

    """
    # Let Google refresh our credentials if necessary.
    credentials = google.oauth2.credentials.Credentials(
        **request.session["credentials"]
    )
    request.session["credentials"] = credentials_to_dict(credentials)

    email = fetch_user_email(credentials)
    return PlainTextResponse(f"User: {email}")


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


def rewrite_scheme(url: str) -> str:
    """Upgrade to https in all non-local test environments.

    This is necessary with hypercorn because it does not properly interpret the
    x-forward headers and thus thinks the requests all have an http scheme.
    """
    is_prod = not dfh.api.isLocalDev()
    if is_prod and url.startswith("http://"):
        return url.replace("http://", "https://")
    return url


@router.get("/authdemo")
def authdemo():
    return HTMLResponse(print_index_table())


@router.get("/google-login")
def authorize(request: Request):
    """Initiate the authentication flow.

    Here is a summary of how this works:

     - user hits this URL.
     - this handler will initiate the Google OAuth flow and return a redirect
       to Google's authentication endpoint.
     - The frontend will redirect the user to the Google login.
     - The Google login page will return another redirect response. This time
       it will target our own `/oauth2callback` and provide it with
       credentials.
     - In that `oauth2callback` we will then verify ourselves that the token is
       authentic by asking Google if it is.
     - We will then mint a new JWT signed with our own secret and install that
       as a session cookie. This will allow us to identify all users that
       communicate via the frontend.

    NOTE: This code is verbatim from
    https://developers.google.com/identity/protocols/oauth2/web-server#example
    with trivial changes to adapt it from Flask to FastAPI.

    """
    cfg: ServerConfig = request.app.extra["config"]

    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        cfg.google_client_secrets_file, scopes=SCOPES
    )

    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = request.url_for("oauth2callback")

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type="offline",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )

    # Store the state so the callback can verify the auth server response.
    request.session["state"] = state

    return RedirectResponse(url=authorization_url)


@router.get("/oauth2callback")
def oauth2callback(request: Request):
    """Implement the OAuth2 callback.

    After the user authenticated himself with Google in the frontend, Google
    will send a redirect response

    NOTE: This code is verbatim from
    https://developers.google.com/identity/protocols/oauth2/web-server#example
    with trivial changes to adapt it from Flask to FastAPI.

    """
    cfg: ServerConfig = request.app.extra["config"]

    # Specify the state when creating the flow in the callback so that it can
    # be verified in the authorization server response.
    state = request.session["state"]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        cfg.google_client_secrets_file, scopes=SCOPES, state=state
    )
    flow.redirect_uri = request.url_for("oauth2callback")

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    resp_url = rewrite_scheme(str(request.url))
    flow.fetch_token(authorization_response=resp_url)

    # Store session credentials.
    creds = cast(google.oauth2.credentials.Credentials, flow.credentials)
    request.session["credentials"] = credentials_to_dict(creds)

    # Add the user's email to the session. This is handy for the frontend
    # but has no meaning for the authentication flow.
    request.session["email"] = fetch_user_email(creds)
    return RedirectResponse(url=request.url_for("test_api_request"))


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
    del request.session["credentials"]

    if resp.status_code == 200:
        return "Credentials successfully revoked."
    else:
        return "Could not revoke credentials."


@router.get("/clear-session")
def clear_session_credentials(request: Request):
    """Clear the browser session."""
    if "credentials" in request.session:
        del request.session["credentials"]
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
