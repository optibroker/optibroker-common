import logging

import requests
from flask import abort

logger = logging.getLogger(__name__)


def get_keycloak_admin_token(server_url, client_id, admin_username, admin_password):
    """
    Retrieve the admin token from the Keycloak server.

    Args:
        server_url: Base URL of the Keycloak server.
        client_id: Client ID for the admin token request.
        admin_username: Keycloak admin username.
        admin_password: Keycloak admin password.

    Returns:
        str: The access token if the request is successful.
    """
    token_url = f"{server_url}/realms/master/protocol/openid-connect/token"

    payload = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': admin_username,
        'password': admin_password
    }

    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        abort(503, description=f"Failed to retrieve Keycloak admin token: {http_err}")
    except requests.exceptions.RequestException as req_err:
        abort(500, description=f"Request to Keycloak server failed: {req_err}")

    return response.json().get('access_token')


def get_keycloak_realms(server_url, client_id, admin_username, admin_password):
    """
    Retrieve a list of realms from Keycloak, excluding the 'master' realm.

    Args:
        server_url: Base URL of the Keycloak server.
        client_id: Client ID for the admin token request.
        admin_username: Keycloak admin username.
        admin_password: Keycloak admin password.

    Returns:
        list: A list of realm names, excluding 'master'.
    """
    token = get_keycloak_admin_token(server_url, client_id, admin_username, admin_password)

    headers = {
        'Authorization': f"Bearer {token}"
    }
    realms_url = f"{server_url}/admin/realms"
    response = requests.get(realms_url, headers=headers)
    response.raise_for_status()

    return [realm['realm'] for realm in response.json() if realm['realm'] != 'master']


def create_keycloak_user(server_url, client_id, admin_username, admin_password,
                         realm, forename, surname, email=None, username=None, enabled=True):
    """
    Create a new user in Keycloak.

    Args:
        server_url: Base URL of the Keycloak server.
        client_id: Client ID for the admin token request.
        admin_username: Keycloak admin username.
        admin_password: Keycloak admin password.
        realm: Realm in which to create the user.
        forename: First name of the user.
        surname: Last name of the user.
        email: Email address of the user.
        username: Username for the user. Defaults to 'forename.surname'.
        enabled: Whether the user account is enabled. Defaults to True.

    Returns:
        str: The ID of the created user in Keycloak.
    """
    token = get_keycloak_admin_token(server_url, client_id, admin_username, admin_password)

    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    auto_generated_username = username or f"{forename.lower()}.{surname.lower()}"

    user_payload = {
        "firstName": forename,
        "lastName": surname,
        "enabled": enabled,
        "username": auto_generated_username,
    }

    if email:
        user_payload["email"] = email

    user_url = f"{server_url}/admin/realms/{realm}/users"

    try:
        response = requests.post(user_url, json=user_payload, headers=headers)
        response.raise_for_status()
        user_id = response.headers.get("Location").split("/")[-1]
        return user_id

    except requests.exceptions.HTTPError:
        logger.error("Keycloak response: %s %s", response.status_code, response.text)
        abort(503, description=f"Failed to create user in Keycloak: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as req_err:
        abort(500, description=f"Request to Keycloak server failed: {req_err}")
