import base64
import json
from typing import Optional


def strip_bearer_prefix(token: str) -> str:
    """Remove 'Bearer ' prefix from token if present.

    Args:
        token: Token string that may contain "Bearer " prefix

    Returns:
        Token without "Bearer " prefix
    """
    return token[7:] if token.lower().startswith("bearer ") else token


def extract_delegation_chain_from_jwt(token: str) -> tuple[Optional[str], list[str]]:
    """Extract subject and delegation chain from JWT token.

    Parses JWT tokens containing delegation information per RFC 8693.
    Returns the primary subject and the chain of actors who acted on behalf.

    Args:
        token: JWT token string (with or without "Bearer " prefix)

    Returns:
        A tuple of (subject, actors) where:
        - subject: The end user or resource owner (from `sub` field)
        - actors: Chain of intermediaries who acted on behalf (from nested `act` claims)

    Examples:
        ```python
        # User → Agent1 → Agent2
        subject, actors = extract_delegation_chain_from_jwt(token)
        # Returns: ("user1", ["agent2", "agent1"])
        # Meaning: user1 delegated to agent1, who delegated to agent2
        ```
    """
    try:
        # Remove "Bearer " prefix if present
        token = strip_bearer_prefix(token)

        # JWT token has 3 parts separated by dots: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return None, []

        # Decode payload (second part)
        payload_part = parts[1]

        # Add padding for base64url decoding (JWT doesn't use padding)
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += "=" * (4 - missing_padding)

        # Decode base64 and parse JSON
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload: dict = json.loads(decoded_bytes.decode("utf-8"))

        # Extract subject from JWT
        subject = payload.get("sub")
        if not subject:
            return None, []

        # Extract actor chain from nested "act" claims
        actors = []
        current_act = payload.get("act")
        while current_act and isinstance(current_act, dict):
            actor_sub = current_act.get("sub")
            if actor_sub:
                actors.append(str(actor_sub))
            # Move to next level in the chain
            current_act = current_act.get("act")

        return str(subject), actors

    except (ValueError, json.JSONDecodeError, Exception):
        return None, []
