import base64
import json
import logging

import itsdangerous
import pydantic
from fastapi import HTTPException, Request, status

import dfh.routers.dependencies as dep
from dfh.models import UAMDatabase, UAMGroup, UserToken

logit = logging.getLogger("app")

UAM_DB: UAMDatabase = UAMDatabase(users={}, groups={})


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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in"
    )


def can_login(email: str):
    # Convenience.
    db = dep.UAM_DB
    err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid user <{email}>"
    )

    # Abort if the email is empty.
    if email == "":
        raise err

    # Root user can always login.
    if email == db.root.owner:
        return

    # Special case: disable authorisation.
    if db.root.owner == "*":
        return

    # `email` must be a member of the magic `dfhlogin` group. Grant access only
    # if that group exists and the user is a member.
    try:
        logingroup: UAMGroup = db.root.children["dfhlogin"]
    except KeyError:
        raise err

    def walk(group: UAMGroup) -> bool:
        """Return `True` if and only if `email` is present in at least one
        descendant of `group`.
        """
        if email in group.users:
            return True

        found = False
        for child in group.children.values():
            found = found or walk(child)
        return found

    # Admit login if user is a member of the `dfhlogin` hierarchy.
    if walk(logingroup):
        return
    raise err
