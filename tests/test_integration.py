import json
from pathlib import Path
import time
import pytest

from mini_redis.config import ServerConfig
from mini_redis.core.dispatcher import CommandDispatcher, default_handlers
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.main import _build_maintenance_step, create_components
from mini_redis.persistence.snapshot import SnapshotError, SnapshotManager, SnapshotRecord
from mini_redis.protocol.resp_types import BulkString, Integer, NullBulkString, RespError, SimpleString


def make_dispatcher() -> CommandDispatcher:
    storage = Storage()
    storage.set_expiration_checker(get_expiration_manager().is_expired)
    dispatcher = CommandDispatcher(storage=storage)
    dispatcher.register_many(default_handlers())
    return dispatcher


def test_ttl_flow_through_dispatcher() -> None:
    expiration_manager = get_expiration_manager()
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["SET", "foo", "bar"]) == SimpleString("OK")
    expiration_manager.set_current_time(100.0)
    assert dispatcher.dispatch(["EXPIRE", "foo", "3"]) == Integer(1)
    assert dispatcher.dispatch(["TTL", "foo"]) == Integer(3)
    expiration_manager.set_current_time(104.0)
    assert dispatcher.dispatch(["GET", "foo"]) == NullBulkString()
    assert dispatcher.dispatch(["TTL", "foo"]) == Integer(-2)
    expiration_manager.set_current_time(None)


def test_ttl_commands_handle_invalid_input() -> None:
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["EXPIRE", "foo"]) == RespError("wrong number of arguments")
    assert dispatcher.dispatch(["EXPIRE", "foo", "NaN"]) == RespError("invalid argument")


def test_basic_commands_still_work_with_ttl_storage() -> None:
    dispatcher = make_dispatcher()

    assert dispatcher.dispatch(["PING"]) == SimpleString("PONG")
    assert dispatcher.dispatch(["SET", "foo", "bar"]) == SimpleString("OK")
    assert dispatcher.dispatch(["GET", "foo"]) == BulkString("bar")
    assert dispatcher.dispatch(["EXISTS", "foo", "missing"]) == Integer(1)
    assert dispatcher.dispatch(["DEL", "foo"]) == Integer(1)


def make_snapshot_manager(
    snapshot_path: Path,
    storage: Storage,
    *,
    interval_seconds: float = 30.0,
    time_fn=time.time,
) -> SnapshotManager:
    return SnapshotManager(
        snapshot_path=snapshot_path,
        export_entries=storage.export_entries,
        restore_entries=storage.restore_entries,
        interval_seconds=interval_seconds,
        time_fn=time_fn,
    )


def test_snapshot_round_trip_and_normalized_load(tmp_path: Path) -> None:
    expiration_manager = get_expiration_manager()
    expiration_manager.set_current_time(100.0)
    try:
        snapshot_path = tmp_path / "snapshot.json"
        storage = Storage()
        storage.set_expiration_checker(expiration_manager.is_expired)
        storage.set("foo", "bar")
        storage.set_expire_at("foo", expiration_manager.build_expire_at(30))
        manager = make_snapshot_manager(
            snapshot_path,
            storage,
            time_fn=expiration_manager.now,
        )

        manager.save_now()

        restored_storage = Storage()
        restored_storage.set_expiration_checker(expiration_manager.is_expired)
        restored_manager = make_snapshot_manager(
            snapshot_path,
            restored_storage,
            time_fn=expiration_manager.now,
        )
        records = restored_manager.load_entries()
        restored_manager.restore_from_disk()

        assert isinstance(records["foo"], SnapshotRecord)
        assert restored_storage.get("foo") == "bar"
        ttl = expiration_manager.ttl(restored_storage.get_entry("foo"))
        assert 0 < ttl <= 30
    finally:
        expiration_manager.set_current_time(None)


@pytest.mark.parametrize(
    "payload",
    [
        ["not-a-dict"],
        {"foo": "bar"},
        {"foo": {"expire_at": None}},
        {"foo": {"value": "bar"}},
        {"foo": {"value": "bar", "expire_at": "soon"}},
    ],
)
def test_invalid_schema_causes_startup_failure(tmp_path: Path, payload: object) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
    config = ServerConfig(snapshot_path=snapshot_path)

    with pytest.raises(SnapshotError):
        create_components(config)


def test_expired_entries_are_filtered_on_load(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "expired": {"value": "gone", "expire_at": 10.0},
                "alive": {"value": "here", "expire_at": 200.0},
                "persisted": {"value": "forever", "expire_at": None},
            }
        ),
        encoding="utf-8",
    )
    storage = Storage()
    manager = make_snapshot_manager(snapshot_path, storage, time_fn=lambda: 100.0)

    records = manager.load_entries()

    assert "expired" not in records
    assert records["alive"] == SnapshotRecord(value="here", expire_at=200.0)
    assert records["persisted"] == SnapshotRecord(value="forever", expire_at=None)


def test_missing_snapshot_loads_empty_state(tmp_path: Path) -> None:
    storage = Storage()
    manager = make_snapshot_manager(tmp_path / "missing.json", storage)

    assert manager.load_entries() == {}


def test_dispatcher_and_snapshot_restore_integration(tmp_path: Path) -> None:
    expiration_manager = get_expiration_manager()
    expiration_manager.set_current_time(100.0)
    try:
        snapshot_path = tmp_path / "snapshot.json"
        dispatcher = make_dispatcher()

        assert dispatcher.dispatch(["SET", "foo", "bar"]) == SimpleString("OK")
        assert dispatcher.dispatch(["EXPIRE", "foo", "5"]) == Integer(1)

        manager = make_snapshot_manager(
            snapshot_path,
            dispatcher.storage,
            time_fn=expiration_manager.now,
        )
        manager.save_now()

        restored_storage = Storage()
        restored_storage.set_expiration_checker(expiration_manager.is_expired)
        restored_manager = make_snapshot_manager(
            snapshot_path,
            restored_storage,
            time_fn=expiration_manager.now,
        )
        restored_manager.restore_from_disk()
        restored_dispatcher = CommandDispatcher(storage=restored_storage)
        restored_dispatcher.register_many(default_handlers())

        assert restored_dispatcher.dispatch(["GET", "foo"]) == BulkString("bar")
        ttl_reply = restored_dispatcher.dispatch(["TTL", "foo"])
        assert isinstance(ttl_reply, Integer)
        assert 0 < ttl_reply.value <= 5
    finally:
        expiration_manager.set_current_time(None)


def test_atomic_write_failure_preserves_existing_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    original_payload = {"seed": {"value": "old", "expire_at": None}}
    snapshot_path.write_text(json.dumps(original_payload, sort_keys=True), encoding="utf-8")
    storage = Storage()
    storage.set("foo", "bar")
    manager = make_snapshot_manager(snapshot_path, storage)

    def broken_write(temp_file, payload):
        temp_file.write('{"broken":')
        raise RuntimeError("boom")

    monkeypatch.setattr(manager, "_write_payload", broken_write)

    with pytest.raises(RuntimeError):
        manager.save_now()

    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == original_payload


def test_snapshot_due_is_reported_without_background_thread(tmp_path: Path) -> None:
    current_time = [100.0]
    storage = Storage()
    manager = make_snapshot_manager(
        tmp_path / "snapshot.json",
        storage,
        interval_seconds=30.0,
        time_fn=lambda: current_time[0],
    )

    assert manager.autosave_enabled() is True
    assert manager.next_snapshot_at(None) == 130.0
    assert manager.should_snapshot(None, now=129.9) is False
    assert manager.should_snapshot(None, now=130.0) is True
    assert manager.next_snapshot_at(130.0) == 160.0
    assert manager.should_snapshot(130.0, now=159.9) is False
    assert manager.should_snapshot(130.0, now=160.0) is True


def test_snapshot_due_is_disabled_when_interval_is_zero(tmp_path: Path) -> None:
    storage = Storage()
    manager = make_snapshot_manager(tmp_path / "snapshot.json", storage, interval_seconds=0.0)

    assert manager.autosave_enabled() is False
    assert manager.next_snapshot_at(None) is None
    assert manager.should_snapshot(None, now=100.0) is False


def test_final_save_still_writes_snapshot_without_background_autosave(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    storage = Storage()
    storage.set("foo", "bar")
    manager = make_snapshot_manager(snapshot_path, storage, interval_seconds=0.0)

    manager.final_save()

    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["foo"]["value"] == "bar"


def test_maintenance_step_cleans_expired_keys_and_saves_snapshot(tmp_path: Path) -> None:
    expiration_manager = get_expiration_manager()
    expiration_manager.set_current_time(100.0)
    try:
        snapshot_path = tmp_path / "snapshot.json"
        storage = Storage()
        storage.set_expiration_checker(expiration_manager.is_expired)
        storage.set("expired", "gone")
        storage.set("alive", "here")
        storage.set_expire_at("expired", expiration_manager.build_expire_at(1))
        storage.set_expire_at("alive", expiration_manager.build_expire_at(20))

        manager = make_snapshot_manager(
            snapshot_path,
            storage,
            interval_seconds=30.0,
            time_fn=expiration_manager.now,
        )
        maintenance_step = _build_maintenance_step(storage, manager)

        expiration_manager.set_current_time(102.0)
        maintenance_step(130.0)

        assert storage.get("expired") is None
        assert storage.get("alive") == "here"

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert "expired" not in payload
        assert payload["alive"]["value"] == "here"
    finally:
        expiration_manager.set_current_time(None)
