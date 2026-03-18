# Mini Redis (RESP 기반) 프로젝트

## 프로젝트 개요

본 프로젝트는 Redis와 유사한 동작을 하는 RESP 프로토콜 기반 Mini Redis 서버를 Python으로 구현하는 것을 목표로 합니다.

이 프로젝트는 단순한 HTTP API 서버가 아니라, 다음과 같은 구조를 갖는 Redis-like 서버를 구현하는 데 목적이 있습니다.

- TCP 기반 서버
- RESP 프로토콜 직접 구현
- 다중 클라이언트 연결 처리
- TTL(만료 정책) 지원
- 선택적으로 persistence 기능 지원

---

## 전체 아키텍처

```text
[Client]
   |
   v
[TCP Server]
   |
   v
[RESP Parser]
   |
   v
[Command Dispatcher]
   |
   v
[Storage Engine]
   |
   +-- Expiration Manager (TTL)
   |
   +-- Persistence Manager (Optional)
```

---

## 목표 기능

### 필수 기능 (MVP)

- TCP 서버 구현
- RESP 요청 파싱 및 응답 직렬화
- 기본 명령어 지원
  - `PING`
  - `SET key value`
  - `GET key`
  - `DEL key`
  - `EXISTS key`
- TTL 관련 명령어 지원
  - `EXPIRE key seconds`
  - `TTL key`
  - `PERSIST key`
- Lazy expiration

### 확장 기능 (Optional)

- Snapshot persistence
- Append Only File(AOF)
- Background expiration cleanup
- `INCR`, `DECR`
- `redis-cli` 연동 시도

---

## 4인 협업 구조

이 프로젝트는 계층 기반으로 역할을 분리하여 4명이 병렬로 개발할 수 있도록 설계합니다.

| 역할 | 담당 영역 | 핵심 책임 |
|---|---|---|
| 1번 | 네트워크 / RESP | TCP 서버, 세션 처리, RESP 파서/직렬화 |
| 2번 | 코어 / 저장소 | Storage Engine, Dispatcher, 기본 명령 처리 |
| 3번 | TTL / 만료 | Expiration 정책, EXPIRE/TTL/PERSIST |
| 4번 | Persistence / 배포 / 테스트 | Snapshot/AOF, EC2 배포, 통합 테스트 |

---

## 1번 담당: 네트워크 / RESP 프로토콜

### 역할 설명

클라이언트와 서버 간의 TCP 통신, RESP 파싱, RESP 응답 직렬화를 담당합니다.

### 주요 작업

- TCP 서버 구현
- 클라이언트 연결 수락
- 세션별 입력 버퍼 관리
- RESP 요청 파싱
- RESP 응답 직렬화
- 잘못된 입력에 대한 에러 응답 처리

### RESP 요청 예시

```text
*2\r\n
$3\r\n
GET\r\n
$3\r\n
key\r\n
```

파싱 결과:

```python
["GET", "key"]
```

### RESP 응답 예시

```text
+OK\r\n
$5\r\n
hello\r\n
:1\r\n
$-1\r\n
-ERR unknown command\r\n
```

### 추천 파일 구조

```text
protocol/
  parser.py
  serializer.py
  resp_types.py

server/
  tcp_server.py
  session.py
```

### 완료 기준

- 클라이언트가 TCP로 접속 가능하다.
- RESP 요청을 받아 명령어 배열 형태로 파싱할 수 있다.
- 내부 응답 객체를 RESP 바이트로 직렬화할 수 있다.

---

## 2번 담당: 코어 / Dispatcher / Storage Engine

### 역할 설명

Mini Redis의 핵심 데이터 저장소와 명령 처리 로직을 담당합니다.

### 주요 작업

- 저장소 자료구조 설계
- `SET`, `GET`, `DEL`, `EXISTS`, `PING` 구현
- Command Dispatcher 구현
- 인자 개수 검증 및 에러 처리
- 공통 내부 모델 정의

### 내부 데이터 구조 예시

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Entry:
    value: str
    expire_at: Optional[float] = None
```

```python
store: dict[str, Entry]
```

### 추천 파일 구조

```text
core/
  models.py
  storage.py
  dispatcher.py
  commands/
    basic.py
    keyspace.py
```

### 완료 기준

- 명령어 리스트를 입력받아 적절한 내부 응답 객체를 반환할 수 있다.
- 기본 CRUD 동작이 정상적으로 수행된다.

---

## 3번 담당: TTL / Expiration / Invalidation

### 역할 설명

키의 만료 시간과 무효화 정책을 담당합니다.

### 주요 작업

- `EXPIRE key seconds`
- `TTL key`
- `PERSIST key`
- Lazy expiration 구현
- Optional: background cleanup loop 구현
- 만료된 키 접근 시 자동 삭제 처리

### TTL 동작 규약

| 상태 | 반환값 |
|---|---|
| 키가 없음 | `-2` |
| 키는 있으나 TTL 없음 | `-1` |
| TTL 존재 | 남은 초(integer) |

### 추천 파일 구조

```text
expiration/
  manager.py
  cleanup.py
  ttl_commands.py
```

### 완료 기준

- `SET -> EXPIRE -> TTL -> 만료 -> GET nil` 흐름이 정상 동작한다.
- 만료된 key는 조회 시 자동 삭제된다.

---

## 4번 담당: Persistence / 배포 / 테스트

### 역할 설명

데이터 복구, 서버 운영 환경, 통합 테스트를 담당합니다.

### 주요 작업

- Snapshot 저장 및 로드
- Optional: AOF 구현
- 서버 시작 시 복구 로직 연결
- Dockerfile 작성
- EC2 배포
- 통합 테스트 작성
- 실행 방법 및 시연 문서화

### Snapshot 예시 형식

```json
{
  "foo": {
    "value": "bar",
    "expire_at": 1700000000.0
  }
}
```

### 추천 파일 구조

```text
persistence/
  snapshot.py
  aof.py

tests/
  test_protocol.py
  test_storage.py
  test_ttl.py
  test_integration.py

Dockerfile
README.md
```

### 완료 기준

- 서버 재시작 후 snapshot 기반 복구가 가능하다.
- EC2에서 외부 클라이언트가 접속 가능하다.
- 기본 통합 테스트가 통과한다.

---

## 역할 간 의존 관계

```text
[Protocol / Server]
        |
        v
[Dispatcher / Storage]
        |
        v
[TTL / Expiration]
        |
        v
[Persistence / Deploy / Test]
```

핵심 중심축은 2번 역할(코어 / 저장소)입니다.  
1번, 3번, 4번은 모두 코어 인터페이스 위에 연결되는 구조를 갖습니다.

---

## 협업 전 반드시 합의해야 하는 사항

### 1. 내부 데이터 구조

```python
Entry(value, expire_at)
```

### 2. 명령어 내부 표현

```python
["SET", "key", "value"]
["GET", "key"]
["EXPIRE", "key", "10"]
```

### 3. 응답 객체 규약

```python
SimpleString("OK")
BulkString("hello")
Integer(1)
NullBulkString()
RespError("wrong number of arguments")
```

### 4. 에러 메시지 규약

```text
-ERR wrong number of arguments
-ERR unknown command
-ERR invalid argument
```

---

## 디렉토리 구조

```text
mini_redis/
├── main.py
├── config.py
├── protocol/
│   ├── parser.py
│   ├── serializer.py
│   └── resp_types.py
├── server/
│   ├── tcp_server.py
│   └── session.py
├── core/
│   ├── models.py
│   ├── storage.py
│   ├── dispatcher.py
│   └── commands/
│       ├── basic.py
│       └── ttl.py
├── expiration/
│   ├── manager.py
│   └── cleanup.py
├── persistence/
│   ├── snapshot.py
│   └── aof.py
├── tests/
│   ├── test_protocol.py
│   ├── test_storage.py
│   ├── test_ttl.py
│   └── test_integration.py
├── scripts/
│   └── run_server.sh
├── Dockerfile
└── README.md
```

---

## 개발 일정 예시

### Day 1
- 전체 설계 회의
- 지원 명령어 확정
- 내부 데이터 구조 확정
- 응답 객체 규약 확정
- 디렉토리 구조 및 브랜치 전략 결정

### Day 2
- 각 파트별 개발 시작
- 코어/프로토콜 뼈대 구현

### Day 3
- TCP 서버와 Dispatcher 연결
- 기본 명령어 end-to-end 동작 확인

### Day 4
- TTL 및 persistence 통합
- 예외 처리 및 테스트 보강

### Day 5
- EC2 배포
- 문서 정리
- 시연 및 발표 준비

---

## 테스트 시나리오

- `PING` → `PONG`
- `SET` → `GET`
- `DEL` → 삭제 확인
- `EXPIRE` → `TTL` 감소 확인
- 만료 후 `GET` → nil 응답
- 서버 재시작 후 snapshot 복구 확인

---

## 실행 예시

```bash
python main.py
```

예상 접속 예시:

```bash
redis-cli -h <EC2-IP> -p <PORT>
```

---

## 발표 포인트

### 1번
RESP 프로토콜을 직접 구현하고 TCP 기반 클라이언트-서버 통신을 설계했다.

### 2번
Storage Engine과 Command Dispatcher를 통해 Redis-like 명령 처리 구조를 설계했다.

### 3번
TTL, lazy expiration, invalidation 정책을 구현했다.

### 4번
Persistence, EC2 배포, 통합 테스트를 통해 실제 사용 가능한 서버 환경으로 확장했다.

---

## 한 줄 요약

Redis를 단순히 사용하는 것이 아니라, Redis의 핵심 구조를 직접 구현하고 팀 단위로 분업 개발하는 프로젝트입니다.
