# 2번 브랜치 연동 가이드

이 문서는 2번 코어/저장소 브랜치 기준으로, 1번과 3번이 바로 붙을 수 있게 연동 규약만 정리한 문서다.

## 현재 합의된 실행 모델

- 이 프로젝트는 lock 기반이 아니라 단일 스레드 event-loop 모델로 간다.
- 저장소 접근은 오직 event-loop 스레드 하나에서만 일어난다고 가정한다.
- 따라서 storage는 의도적으로 lock-free 구조를 유지한다.
- background thread가 live storage를 직접 건드리면 안 된다.
- 1번은 이벤트 루프에서 `dispatch(...)`를 sync call로 호출하고, 3번 TTL도 같은 스레드에서 lazy expiration 또는 tick 방식으로 붙는다.
- 4번 snapshot은 `export_entries()` / `restore_entries()` 훅을 써서 event-loop 경계에서 동기 저장/복구로 연결하는 방향을 전제로 한다.

## 1번에게 보낼 말

아래 기준으로 붙이면 된다.

### 1. 1번이 2번에서 사용할 진입점

- 사용할 클래스는 `core.dispatcher.CommandDispatcher`다.
- 서버 시작 시 `StorageEngine`과 `CommandDispatcher`를 한 번만 생성해서 재사용하면 된다.
- 요청 1개가 파싱될 때마다 `dispatcher.dispatch(command)`를 호출하면 된다.

```python
from core.dispatcher import CommandDispatcher
from core.storage import StorageEngine

storage = StorageEngine()
dispatcher = CommandDispatcher(storage)

response = dispatcher.dispatch(["SET", "foo", "bar"])
```

### 2. 1번이 2번에게 넘겨야 하는 입력 형식

- 입력 형식은 `list[str]`다.
- 첫 원소는 명령어고, 나머지는 인자다.
- 2번 디스패처가 내부에서 모두 `str()`로 정규화하므로 숫자가 와도 문자열로 바뀐다.

예시:

```python
["PING"]
["SET", "foo", "bar"]
["GET", "foo"]
["DEL", "foo"]
["EXISTS", "foo"]
["EXPIRE", "foo", "10"]
["TTL", "foo"]
["PERSIST", "foo"]
```

### 3. 1번이 2번으로부터 받는 응답 형식

응답은 `core.models.Response` 중 하나다.

- `SimpleString("OK")`
- `BulkString("hello")`
- `Integer(1)`
- `NullBulkString()`
- `RespError("wrong number of arguments")`

### 4. 1번이 RESP로 직렬화할 때 기준

- `SimpleString("OK")` -> `+OK\r\n`
- `BulkString("hello")` -> `$5\r\nhello\r\n`
- `Integer(1)` -> `:1\r\n`
- `NullBulkString()` -> `$-1\r\n`
- `RespError("wrong number of arguments")` -> `-ERR wrong number of arguments\r\n`

즉, `RespError`의 `message`에는 `ERR` 접두어가 없고, 1번 serializer가 `-ERR `를 붙여서 바이트로 만들어야 한다.

### 5. 1번이 구현할 때 주의할 점

- 2번 코드는 동기 호출 기준이다. `dispatcher.dispatch(...)`를 그대로 sync call로 쓰면 된다.
- 1번은 `core/_store` 같은 내부 구현을 만지지 않는다.
- 1번은 명령어 파싱과 응답 직렬화만 담당하고, 비즈니스 로직은 전부 dispatcher에 넘긴다.
- unknown command, wrong number of arguments 같은 기본 에러 판단은 2번 dispatcher/handler가 처리한다.

### 6. 1번에게 실제로 보낼 문구

```text
2번 브랜치 기준 연동 포인트는 CommandDispatcher 하나입니다.

서버 시작 시 StorageEngine + CommandDispatcher를 한 번 생성하고,
RESP 파싱 결과를 list[str] 형태로 dispatcher.dispatch(command)에 넘기면 됩니다.

예:
["SET", "foo", "bar"]
["GET", "foo"]
["EXPIRE", "foo", "10"]

응답은 SimpleString / BulkString / Integer / NullBulkString / RespError 중 하나로 오고,
1번 쪽 serializer가 아래 규칙으로 RESP 바이트로 바꾸면 됩니다.

SimpleString -> +...\r\n
BulkString -> $len\r\n...\r\n
Integer -> :...\r\n
NullBulkString -> $-1\r\n
RespError(message) -> -ERR {message}\r\n

2번 코드는 sync call 기준이라 그대로 붙이면 됩니다.
```

## 3번에게 보낼 말

아래 기준으로 붙이면 된다.

### 1. Entry 모델 규약

- 위치: `core/models.py`
- 형태: `Entry(value, expire_at)`
- 타입: `value: str`, `expire_at: None | float`
- `expire_at`은 unix timestamp float 기준으로 쓰면 된다.

### 2. 3번이 써야 하는 Storage 공개 메서드

3번은 내부 저장소를 직접 접근하지 않고 아래 메서드만 사용한다.

- `set(key, value)`
- `get(key)`
- `get_entry(key)`
- `delete(key)`
- `exists(key)`
- `set_expire_at(key, expire_at)`
- `clear_expire_at(key)`
- `keys()`
- `size()`
- `set_expiration_checker(expiration_checker)`

주의:

- `storage._store` 직접 접근 금지
- TTL 구현은 Storage API 위에서만 작업

### 3. lazy expiration 책임 분리

- 만료 판정 책임은 3번 ExpirationManager 쪽이다.
- 실제 삭제 책임은 2번 Storage 쪽이다.
- 연결 방식은 `expiration_checker: Callable[[Entry], bool]`를 storage에 주입하는 방식이다.

예:

```python
import time

def is_expired(entry):
    return entry.expire_at is not None and entry.expire_at <= time.time()

storage.set_expiration_checker(is_expired)
```

이렇게 연결하면 아래 메서드 호출 시 storage가 자동으로 만료 체크 후 삭제한다.

- `get`
- `get_entry`
- `exists`
- `keys`
- `size`

즉, 3번은 "만료 여부 판단"만 제공하고, "만료 시 삭제"는 storage가 수행한다.

### 4. Dispatcher 연결 방식

3번은 TTL 명령을 dispatcher에 등록해서 붙이면 된다.

- `dispatcher.register("EXPIRE", handle_expire)`
- `dispatcher.register("TTL", handle_ttl)`
- `dispatcher.register("PERSIST", handle_persist)`

또는:

```python
dispatcher.register_many(
    {
        "EXPIRE": handle_expire,
        "TTL": handle_ttl,
        "PERSIST": handle_persist,
    }
)
```

### 5. TTL 핸들러 시그니처

핸들러 시그니처는 아래로 고정한다.

```python
def handle_ttl(storage: StorageEngine, command: list[str]) -> Response:
    ...
```

입력 예시:

- `["EXPIRE", "foo", "10"]`
- `["TTL", "foo"]`
- `["PERSIST", "foo"]`

2번 dispatcher가 내부에서 `str()` 정규화를 하기 때문에, 인자는 모두 문자열이라고 보면 된다.

### 6. TTL 동작 규약

- 키가 없으면 `Integer(-2)`
- 키는 있는데 TTL이 없으면 `Integer(-1)`
- TTL이 있으면 남은 초를 `Integer(n)`으로 반환
- `EXPIRE` 성공 시 `Integer(1)`, 실패 시 `Integer(0)`
- `PERSIST` 성공 시 `Integer(1)`, 실패 시 `Integer(0)`

### 7. 3번에게 실제로 보낼 문구

```text
2번 브랜치 기준 TTL 연동 규약은 아래와 같습니다.

Entry 모델은 core/models.py의 Entry(value, expire_at)를 그대로 사용하고,
expire_at 타입은 None | float로 고정합니다.

3번은 storage 내부 dict를 직접 만지지 말고 아래 공개 메서드만 사용하면 됩니다.
get, set, delete, exists, get_entry, set_expire_at, clear_expire_at, keys, size, set_expiration_checker

lazy expiration 책임은 분리되어 있습니다.
만료 판정은 3번 ExpirationManager가 하고,
실제 삭제는 2번 Storage가 get/get_entry/exists/keys/size 호출 시 자동 처리합니다.

Dispatcher 연결은 register 또는 register_many로 붙이면 됩니다.
예:
dispatcher.register("EXPIRE", handle_expire)
dispatcher.register("TTL", handle_ttl)
dispatcher.register("PERSIST", handle_persist)

핸들러 시그니처는
handle_xxx(storage, command: list[str]) -> Response
형태로 맞추면 됩니다.

command 예시는 아래와 같습니다.
["EXPIRE", "foo", "10"]
["TTL", "foo"]
["PERSIST", "foo"]
```
