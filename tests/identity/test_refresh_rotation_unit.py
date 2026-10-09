from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from src.repositories.identity.refresh_token_repository import RefreshTokenRepository
from src.services.identity.auth_service import AuthService


@pytest.fixture
def auth(monkeypatch):
    user = SimpleNamespace(id=uuid4(), email="rotation@example.com")
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    repository = SimpleNamespace(
        session=session,
        consume_if_valid=AsyncMock(return_value=True),
        create=AsyncMock(),
        get_by_token=AsyncMock(return_value=SimpleNamespace(user_id=user.id)),
        revoke_token=AsyncMock(),
    )
    users = SimpleNamespace(session=session, get_by_email=AsyncMock(return_value=user))
    monkeypatch.setattr(
        "src.services.identity.auth_service.verify_token",
        lambda *_: {"sub": user.email, "type": "refresh"},
    )
    return AuthService(users, repository), repository, session, user


async def test_rotation_commits_only_after_successor_is_persisted(auth):
    service, repository, session, user = auth
    calls = Mock()
    calls.attach_mock(repository.consume_if_valid, "consume")
    calls.attach_mock(repository.create, "create")
    calls.attach_mock(session.commit, "commit")

    pair = await service.refresh_user_tokens("old-token")

    assert [call[0] for call in calls.mock_calls] == ["consume", "create", "commit"]
    assert repository.consume_if_valid.await_args.args[:2] == ("old-token", user.id)
    assert repository.create.await_args.args[0]["token"] == pair.refresh_token
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("failure_at", ["create", "commit"])
async def test_rotation_rolls_back_persistence_failures(auth, failure_at):
    service, repository, session, _ = auth
    operation = repository.create if failure_at == "create" else session.commit
    operation.side_effect = RuntimeError("injected persistence failure")

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        await service.refresh_user_tokens("old-token")

    session.rollback.assert_awaited_once()
    if failure_at == "create":
        session.commit.assert_not_awaited()


async def test_unsuccessful_claim_never_creates_a_successor(auth):
    service, repository, session, _ = auth
    repository.consume_if_valid.return_value = False

    with pytest.raises(ValueError, match="Invalid refresh token"):
        await service.refresh_user_tokens("already-consumed-token")

    repository.create.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


async def test_login_commits_issued_pair(auth):
    service, repository, session, user = auth
    pair = await service.create_token_pair(user)
    assert repository.create.await_args.args[0]["token"] == pair.refresh_token
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("operation", ["login", "logout"])
async def test_login_and_logout_roll_back_commit_failure(auth, operation):
    service, _, session, user = auth
    session.commit.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        if operation == "login":
            await service.create_token_pair(user)
        else:
            await service.revoke_refresh_token("token", user.id)
    session.rollback.assert_awaited_once()


async def test_logout_commits_revocation_but_rejects_other_owner(auth):
    service, repository, session, user = auth
    assert await service.revoke_refresh_token("token", user.id)
    repository.revoke_token.assert_awaited_once_with("token")
    session.commit.assert_awaited_once()

    session.commit.reset_mock()
    repository.revoke_token.reset_mock()
    assert not await service.revoke_refresh_token("token", uuid4())
    repository.revoke_token.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_repository_claim_has_all_guards_and_does_not_commit():
    result = Mock()
    result.scalar_one_or_none.return_value = uuid4()
    session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
    repository = RefreshTokenRepository(session)
    owner, now = uuid4(), datetime.utcnow()

    assert await repository.consume_if_valid("token", owner, now)

    statement = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "UPDATE refresh_tokens SET" in sql
    assert "refresh_tokens.revoked IS false" in sql
    assert "refresh_tokens.expires_at >" in sql
    assert "refresh_tokens.user_id =" in sql
    assert "refresh_tokens.token =" in sql
    assert "RETURNING refresh_tokens.id" in sql
    assert owner in statement.params.values()
    assert now in statement.params.values()
    session.commit.assert_not_awaited()
