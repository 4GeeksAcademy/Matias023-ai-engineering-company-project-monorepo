"""OWASP A07: los tokens de recuperacion no deben persistir en claro."""

import security


class FakeResetTokensTable:
    def __init__(self):
        self.records = []

    def insert(self, document):
        self.records.append(document)


def test_reset_token_is_not_persisted_in_plaintext(monkeypatch):
    storage = FakeResetTokensTable()
    monkeypatch.setattr(security, "reset_tokens_table", storage)

    token = security.store_reset_token(user_id=101)

    assert len(storage.records) == 1
    assert storage.records[0]["user_id"] == 101
    assert storage.records[0]["used"] is False

    # Esta propiedad debe fallar ANTES de corregir el hallazgo.
    assert token not in storage.records[0].values(), (
        "OWASP A07: el token de recuperacion se guarda en texto original"
    )
