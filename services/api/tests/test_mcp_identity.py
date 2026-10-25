"""Pruebas aisladas para validar JWT OAuth de MCP."""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt

from mcp_identity import MCPIdentityError, validate_mcp_token


@pytest.fixture
def oauth_data():
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    numbers = key.public_key().public_numbers()

    def b64int(number):
        raw = number.to_bytes(
            (number.bit_length() + 7) // 8, "big"
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    jwks = {"keys": [{
        "kty": "RSA",
        "kid": "test-key",
        "alg": "RS256",
        "use": "sig",
        "n": b64int(numbers.n),
        "e": b64int(numbers.e),
    }]}

    now = datetime.now(timezone.utc)
    claims = {
        "sub": "usuario-prueba",
        "iss": "https://issuer.example.test",
        "aud": "trackflow-mcp",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "scope": "incidents:read inventory:read",
    }

    def sign(data):
        return jwt.encode(
            data, private_pem, algorithm="RS256",
            headers={"kid": "test-key"},
        )

    def validate(token, scope="incidents:read"):
        return validate_mcp_token(
            token,
            jwks=jwks,
            issuer="https://issuer.example.test",
            audience="trackflow-mcp",
            required_scope=scope,
        )

    return claims, sign, validate


def test_valid_token(oauth_data):
    claims, sign, validate = oauth_data
    result = validate(sign(claims))
    assert result.subject == "usuario-prueba"


def test_insufficient_scope(oauth_data):
    claims, sign, validate = oauth_data
    with pytest.raises(MCPIdentityError):
        validate(sign(claims), "incidents:write")


def test_wrong_issuer(oauth_data):
    claims, sign, validate = oauth_data
    with pytest.raises(MCPIdentityError):
        validate(sign({
            **claims, "iss": "https://otro.test"
        }))


def test_wrong_audience(oauth_data):
    claims, sign, validate = oauth_data
    with pytest.raises(MCPIdentityError):
        validate(sign({
            **claims, "aud": "otro"
        }))


def test_expired_token(oauth_data):
    claims, sign, validate = oauth_data
    with pytest.raises(MCPIdentityError):
        validate(sign({
            **claims,
            "exp": datetime.now(timezone.utc)
                   - timedelta(minutes=1),
        }))


def test_missing_subject(oauth_data):
    claims, sign, validate = oauth_data
    with pytest.raises(MCPIdentityError):
        validate(sign({**claims, "sub": ""}))
