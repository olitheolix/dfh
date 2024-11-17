import base64
import json
import logging
import os
from functools import wraps
from typing import Annotated, List, Tuple

import google.cloud.spanner as spanner
import itsdangerous
import pydantic
from fastapi import Depends, HTTPException, Request, status
from google.api_core.exceptions import (
    Aborted,
    AlreadyExists,
    DeadlineExceeded,
    FailedPrecondition,
    GoogleAPIError,
    InternalServerError,
    NotFound,
    PermissionDenied,
    ResourceExhausted,
    ServiceUnavailable,
)
from google.cloud.spanner_v1 import Client
from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.transaction import Transaction

from dfh.models import UserToken

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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in"
    )


def get_login_groups(db: Database) -> Tuple[str, List[str], bool]:
    def runme(transaction: Transaction) -> Tuple[str | None, List[str]]:
        # Retrieve the owner of the root group.
        rows = transaction.read(
            table="OrgGroups", columns=["owner"], keyset=spanner.KeySet([["Org"]])
        )
        rows = list(rows)
        root_owner = rows[0][0] if len(rows) == 1 else None

        # Retrieve the members of the `dfhlogin` group.
        # NOTE: this group may legitimately not exist.
        rows = transaction.execute_sql(
            "select user_id from OrgGroupsUsers where group_id=@group",
            params={"group": "dfhlogin"},
            param_types={"group": spanner.param_types.STRING},
        )
        user_emails = [row[0] for row in rows]
        return root_owner, user_emails

    root_owner, user_emails = handle_spanner_exceptions(db.run_in_transaction)(runme)
    if root_owner is None:
        return "@invalid", [], True

    return root_owner, user_emails, False


def can_login(db: Database, email: str):
    # Convenience.
    denied = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid user <{email}>"
    )

    # Abort if the email is empty.
    if email == "":
        raise denied

    root_owner, allowed_users, err = get_login_groups(db)
    if err:
        raise denied

    # Root user can always login.
    if email == root_owner or email in allowed_users:
        return

    # Special case: disable authorisation.
    if root_owner == "*":
        return

    raise denied


def handle_spanner_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPException as e:
            # Re-raise all HTTP exceptions since we only want to deal with
            # Spanner errors and unhandled exceptions here.
            raise e
        except (
            AlreadyExists,
            NotFound,
            Aborted,
            DeadlineExceeded,
            FailedPrecondition,
            PermissionDenied,
            ResourceExhausted,
            ServiceUnavailable,
            InternalServerError,
        ) as e:
            code = 500 if e.code is None else e.code
            logit.error(
                "spanner exception",
                {"component": "spanner", "code": code, "message": e.message},
            )
            raise HTTPException(code, detail=f"spanner: {e.message}")
        except GoogleAPIError as e:
            logit.error(
                "Google API error",
                {"component": "spanner", "message": str(e)},
            )
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"spanner: {e}",
            )
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="unhandled exception",
            )

    return wrapper


def spanner_db(request: Request) -> Database:
    db: Database = request.app.extra["spanner"]
    return db


def create_spanner_client() -> Tuple[Client | None, Database | None, str, bool]:
    try:
        db_name = os.environ["DFH_SPANNER_DATABASE"]
        instance_id = os.environ["DFH_SPANNER_INSTANCE"]
    except KeyError:
        return None, None, "", True

    project = os.environ.get("DFH_GCP_PROJECT", None)
    client = spanner.Client(project=project)
    instance = client.instance(instance_id)
    database = instance.database(db_name)
    return client, database, instance_id, False


d_user = Annotated[str, Depends(is_authenticated)]
d_db = Annotated[Database, Depends(spanner_db)]
