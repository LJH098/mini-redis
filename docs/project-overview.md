# Mini Redis 소개 문서

이 문서는 발표나 팀 공유를 위해, 현재 `mini_redis` 프로젝트를 가독성 좋게 설명하는 소개용 문서다.

## 한눈에 보기

이 프로젝트는 Redis를 아주 작은 범위로 줄여서 직접 구현해 보는 프로젝트다.

핵심 목표는 아래 다섯 가지다.

- TCP 서버를 만든다.
- RESP 프로토콜로 요청과 응답을 주고받는다.
- 메모리 안에 key-value 데이터를 저장한다.
- TTL을 걸어 일정 시간이 지나면 key가 만료되게 한다.
- snapshot으로 데이터를 저장하고 복구할 수 있는 구조를 만든다.

즉, 이 프로젝트는 단순한 Python 딕셔너리가 아니라 아래 구조를 갖는 "작은 Redis 서버"를 만드는 것이다.

```text
클라이언트
-> TCP 연결
-> RESP 요청
-> Command Dispatcher
-> Storage
-> TTL / Persistence
-> RESP 응답
```

---

## Redis가 무엇인가

Redis는 메모리 기반 데이터 저장소 서버다.

보통은 아래와 같이 사용한다.

```text
SET user:1 alice
GET user:1
EXPIRE user:1 10
TTL user:1
```

이 말은 곧 다음을 의미한다.

- Redis는 프로그램 안의 변수처럼 "메모리"에 데이터를 들고 있다.
- 하지만 단순 변수나 라이브러리가 아니라 "서버"다.
- 따라서 여러 클라이언트가 네트워크를 통해 같은 Redis에 접근할 수 있다.
- key-value 저장뿐 아니라 만료 시간, 자료구조, 복구 기능까지 가진다.

Redis의 중요한 특징은 빠르다는 것만이 아니다.

- 네트워크 서버다.
- 명령 기반이다.
- 응답 형식이 명확하다.
- TTL 같은 정책이 있다.
- persistence를 통해 서버 재시작 후에도 일부 상태를 복구할 수 있다.

---

## TCP가 무엇인가

우리 프로젝트는 TCP 위에서 동작한다.

TCP는 "연결 기반 바이트 스트림"이다.

좋은 점은 아래와 같다.

- 데이터 순서가 유지된다.
- 유실 없이 전달하려고 한다.
- 연결이 유지되는 동안 계속 데이터를 주고받을 수 있다.

하지만 한계도 있다.

- TCP는 메시지 경계를 보장하지 않는다.

예를 들어 클라이언트가 명령 두 개를 보냈다고 해서 서버가 꼭 두 번 나눠서 받는 것은 아니다.

- 한 요청이 반만 들어올 수도 있다.
- 요청 두 개가 한 번에 붙어서 들어올 수도 있다.

그래서 서버는 직접 "어디까지가 한 요청인지" 파싱해야 한다.
이 문제를 해결하는 규칙이 RESP다.

---

## RESP가 무엇인가

RESP는 Redis Serialization Protocol이다.

Redis 클라이언트와 서버는 RESP 형식으로 통신한다.

예를 들어 `GET key`는 아래처럼 전송된다.

```text
*2\r\n
$3\r\n
GET\r\n
$3\r\n
key\r\n
```

의미는 이렇다.

- `*2`: 배열 원소가 2개다.
- `$3`: 길이 3인 문자열이 온다.
- `GET`
- `$3`
- `key`

응답도 RESP 형식을 따른다.

- `+OK\r\n`
- `$3\r\nbar\r\n`
- `:1\r\n`
- `$-1\r\n`
- `-ERR unknown command\r\n`

이 프로젝트에서는 아래 응답 타입을 내부 객체로 먼저 만들고, 마지막에 RESP bytes로 직렬화한다.

- `SimpleString`
- `BulkString`
- `Integer`
- `NullBulkString`
- `RespError`

---

## Event Loop가 왜 중요한가

이번 팀 합의에서 가장 중요한 설계 포인트는 "단일 스레드 event-loop"다.

의미는 간단하다.

- 클라이언트는 여러 개 붙을 수 있다.
- 하지만 명령 실행은 event-loop 스레드 하나에서 순서대로 처리한다.

즉 아래처럼 간다.

```text
여러 소켓 연결
-> 이벤트 루프가 준비된 소켓을 하나씩 처리
-> 요청 파싱
-> dispatcher 호출
-> storage 접근
-> 응답 생성
-> 클라이언트로 전송
```

이 구조의 장점은 storage에 lock을 많이 걸지 않아도 된다는 것이다.

왜냐하면 저장소를 동시에 여러 스레드가 건드리지 않기 때문이다.

이 PR에서 2번 역할 코드를 바꾼 이유도 바로 이것이다.

- 기존: `RLock` 기반 storage
- 변경 후: event-loop 전제를 둔 lock-free storage

즉 동시성 문제를 "락으로 방어"하기보다 "실행 모델 자체를 직렬화"해서 줄이는 방향이다.

이건 실제 Redis 철학과도 더 가깝다.

---

## 우리 프로젝트의 현재 구조

실행용 코드는 `mini_redis/` 아래에 있다.

```text
mini_redis/
  main.py
  config.py
  core/
    models.py
    storage.py
    dispatcher.py
    commands/
      basic.py
      ttl.py
  expiration/
    manager.py
    cleanup.py
  protocol/
    parser.py
    serializer.py
    resp_types.py
  persistence/
    snapshot.py
    aof.py
  server/
    tcp_server.py
    session.py
```

각 폴더 책임은 아래와 같다.

### `core/`

Redis의 핵심 저장소와 명령 처리 로직이 들어 있다.

- `models.py`: `Entry(value, expire_at)` 정의
- `storage.py`: 실제 메모리 저장소
- `dispatcher.py`: 명령어를 적절한 handler로 분기
- `commands/basic.py`: `PING`, `SET`, `GET`, `DEL`, `EXISTS`
- `commands/ttl.py`: `EXPIRE`, `TTL`, `PERSIST`

### `expiration/`

TTL 계산과 만료 판단 정책을 담당한다.

- `manager.py`: 현재 시간, expire_at 계산, TTL 계산
- `cleanup.py`: 만료된 키를 정리하는 보조 루프

### `protocol/`

RESP 파싱과 직렬화를 담당한다.

- `parser.py`: RESP 요청 bytes를 명령 배열로 파싱
- `serializer.py`: 내부 응답 객체를 RESP bytes로 직렬화
- `resp_types.py`: 응답 타입 정의

### `persistence/`

데이터 저장과 복구 구조를 담당한다.

- `snapshot.py`: snapshot 저장/복구
- `aof.py`: AOF placeholder

### `server/`

TCP 연결과 세션을 담당한다.

- `tcp_server.py`: 서버 진입점
- `session.py`: 클라이언트별 buffer

---

## 요청 하나가 처리되는 흐름

예를 들어 `SET foo bar` 요청이 온다고 가정하자.

현재 구조상 의도된 처리 흐름은 아래와 같다.

```text
1. 클라이언트가 TCP로 RESP 요청 전송
2. server/session 계층이 bytes를 읽어 buffer에 누적
3. protocol/parser가 bytes를 ["SET", "foo", "bar"]로 파싱
4. core/dispatcher가 "SET" handler를 찾음
5. core/commands/basic.py의 handle_set 호출
6. storage.set("foo", "bar") 실행
7. SimpleString("OK") 반환
8. protocol/serializer가 +OK\r\n 로 직렬화
9. TCP로 응답 전송
```

TTL 요청은 이 흐름에 expiration manager가 추가된다.

예를 들어 `EXPIRE foo 10`은 아래처럼 간다.

```text
EXPIRE 요청
-> dispatcher
-> handle_expire
-> expiration_manager.build_expire_at(10)
-> storage.set_expire_at(key, expire_at)
-> Integer(1)
-> serializer
-> :1\r\n
```

이후 `GET foo` 시점에는 storage가 lazy expiration을 수행한다.

즉 조회 순간 만료를 검사하고, 이미 만료되었으면 지운 뒤 없는 키처럼 응답한다.

---

## 2번 역할이 맡는 핵심

2번 역할은 이 프로젝트의 중심축이다.

핵심 책임은 아래 세 가지다.

- 메모리 저장소 설계
- 명령어 디스패치 설계
- 기본 명령의 비즈니스 로직 구현

특히 현재 2번 코드의 핵심 포인트는 아래다.

### 1. Entry 모델

모든 값은 단순 문자열이 아니라 `Entry(value, expire_at)`로 저장된다.

즉 내부 상태는 이런 형태다.

```python
{
    "foo": Entry(value="bar", expire_at=None)
}
```

이 구조 덕분에 TTL을 나중에 자연스럽게 붙일 수 있다.

### 2. Dispatcher

명령어 이름을 handler 함수에 연결한다.

예를 들어:

- `SET` -> `handle_set`
- `GET` -> `handle_get`
- `TTL` -> `handle_ttl`

즉 dispatcher는 "무슨 일을 할지 결정"하지 않고, "누가 할지 연결"하는 역할이다.

### 3. Storage

실제 데이터를 들고 있는 메모리 저장소다.

이 PR에서 storage는 lock-free로 정리되었다.

의미는 이렇다.

- storage는 단순해야 한다.
- event-loop가 접근을 직렬화해 준다.
- 따라서 storage 내부에서 lock으로 복잡하게 막지 않는다.

### 4. Lazy Expiration

만료된 key를 항상 background thread가 지우는 것이 아니라,
조회 시점에 "이미 만료되었는지" 검사해서 자동 삭제한다.

즉:

- `get_entry()`
- `get()`
- `exists()`
- `keys()`
- `size()`

이런 메서드가 실제로는 "조회 + 만료 검사 + 필요 시 삭제"를 같이 한다.

---

## 현재 코드 상태를 현실적으로 보면

이 프로젝트는 구조적으로는 꽤 잘 나뉘어 있다.
하지만 완성도는 계층마다 다르다.

### 이미 꽤 갖춰진 부분

- core storage / dispatcher 구조
- TTL 계산과 lazy expiration
- RESP 응답 객체와 serializer
- snapshot 저장/복구 구조

### 아직 미완성이거나 조정이 필요한 부분

- `server/tcp_server.py`
  - 현재 브랜치 기준 role1 최종 구현이 아직 반영되지 않음
- `protocol/parser.py`
  - 현재 브랜치 기준으로는 partial input / multi-command 처리까지는 아직 안 들어옴
- `persistence/snapshot.py`
  - autosave background thread가 남아 있음
  - 단일 스레드 event-loop 철학과는 아직 완전히 일치하지 않음
- `persistence/aof.py`
  - placeholder 수준

즉 현재 상태를 정확히 말하면,
"Redis-like 구조를 갖춘 mini redis"는 맞지만,
"완전히 다듬어진 실사용 서버"라고 하긴 아직 이르다.

---

## 발표 때 이렇게 설명하면 좋다

### 프로젝트 한 줄 설명

이 프로젝트는 Redis의 핵심 구조를 TCP, RESP, storage, TTL, persistence 계층으로 나눠 직접 구현한 mini redis 서버입니다.

### 아키텍처 설명

클라이언트 요청은 TCP로 들어오고, RESP 파서가 이를 명령 배열로 바꾼 뒤, dispatcher가 적절한 handler로 넘기고, storage와 TTL 계층이 실제 데이터를 처리합니다.

### 2번 역할 설명

2번은 storage와 dispatcher를 설계해서 이 프로젝트의 중심축을 만들었습니다.  
특히 lock 기반이 아니라 event-loop 단일 스레드 구조를 전제로 storage를 단순한 lock-free 구조로 바꿨고, TTL이 자연스럽게 붙을 수 있도록 `Entry(value, expire_at)` 모델을 유지했습니다.

### 기술적 포인트

- storage는 lock-free
- dispatcher는 sync call
- TTL은 lazy expiration
- snapshot은 export/restore 훅 기반
- RESP 응답은 타입 객체를 통해 직렬화

---

## 읽는 순서 추천

코드를 처음 읽는 사람은 아래 순서가 가장 이해하기 쉽다.

1. `mini_redis/main.py`
2. `mini_redis/core/dispatcher.py`
3. `mini_redis/core/commands/basic.py`
4. `mini_redis/core/storage.py`
5. `mini_redis/core/commands/ttl.py`
6. `mini_redis/expiration/manager.py`
7. `mini_redis/protocol/serializer.py`
8. `mini_redis/protocol/parser.py`
9. `mini_redis/persistence/snapshot.py`

---

## 지금 이 문서의 목적

이 문서는 세 가지 용도로 쓸 수 있다.

- 팀원에게 현재 구조를 소개할 때
- 발표 전에 전체 흐름을 한 번에 정리할 때
- 코드를 읽기 전에 "무엇이 어디에 있는지" 파악할 때

필요하면 다음 문서로 이어서 보완하면 된다.

- 함수별 상세 설명 문서
- 요청 흐름 추적 문서
- 발표용 짧은 요약본
