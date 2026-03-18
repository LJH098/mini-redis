# 3번 역할 구현 계획서

## 전제

- `README.md`는 수정하지 않는다.
- 구현 시 저장소 구조는 `README.md`의 최종 디렉토리 구조를 그대로 사용한다.
- 3번 역할은 TTL / Expiration / Invalidation 담당이며, 범위는 아래 구조 안에서 해결한다.

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

## 담당 목표

- `EXPIRE key seconds`
- `TTL key`
- `PERSIST key`
- Lazy expiration
- 만료된 키 접근 시 자동 삭제
- Optional: background cleanup loop 연결 가능하게 설계

완료 기준은 `SET -> EXPIRE -> TTL -> 만료 -> GET nil` 흐름이 정상 동작하는 것이다.

## 핵심 규약 정리

### 데이터 모델

- 코어의 기본 엔트리 구조는 `Entry(value, expire_at)`를 따른다.
- `expire_at`은 `None` 또는 Unix timestamp(`float`)로 사용한다.

### TTL 반환 규약

- 키가 없으면 `-2`
- 키는 있으나 TTL이 없으면 `-1`
- TTL이 있으면 남은 초를 `integer`로 반환

### 명령 처리 규약

- `EXPIRE key seconds`
  - 대상 키가 없으면 `0`
  - TTL 설정 성공 시 `1`
  - `seconds`가 정수가 아니면 에러 처리
- `TTL key`
  - 규약대로 `-2`, `-1`, 남은 초 반환
- `PERSIST key`
  - 키가 없거나 제거할 TTL이 없으면 `0`
  - TTL 제거 성공 시 `1`

## 구현 파일별 계획

### `mini_redis/core/models.py`

- `Entry`에 `expire_at` 필드가 포함되도록 2번과 규약을 맞춘다.
- TTL 전용 구조를 새로 만들기보다 기존 엔트리 모델을 그대로 확장해서 사용한다.

### `mini_redis/expiration/manager.py`

- TTL 계산과 만료 판정을 담당하는 `ExpirationManager`를 둔다.
- 예상 책임:
  - 현재 시각 기준 만료 여부 판정
  - 남은 TTL 계산
  - 엔트리에 TTL 설정
  - 엔트리에서 TTL 제거
- 핵심 메서드 후보:
  - `is_expired(entry, now=None) -> bool`
  - `set_expire(entry, seconds, now=None) -> None`
  - `ttl(entry, now=None) -> int`
  - `persist(entry) -> bool`

### `mini_redis/core/storage.py`

- 조회 계열 동작에서 lazy expiration이 일어나도록 연결한다.
- 최소 반영 지점:
  - `get`
  - `exists`
  - `delete`
  - 필요 시 `find` 또는 내부 헬퍼
- 설계 원칙:
  - 만료 판정은 `ExpirationManager`
  - 실제 삭제는 `Storage`
- 즉, 저장소가 키를 읽기 전에 만료 여부를 확인하고, 만료되었으면 즉시 제거 후 없는 키처럼 처리한다.

### `mini_redis/core/commands/ttl.py`

- TTL 관련 명령 핸들러를 모은다.
- 구현 대상:
  - `handle_expire(storage, args)`
  - `handle_ttl(storage, args)`
  - `handle_persist(storage, args)`
- 책임:
  - 인자 개수 검증
  - 정수 변환 검증
  - `Storage` / `ExpirationManager` 호출
  - RESP 응답 객체 반환

### `mini_redis/core/dispatcher.py`

- `EXPIRE`, `TTL`, `PERSIST`를 등록한다.
- 기본 명령 체계와 동일한 방식으로 분기되게 맞춘다.

### `mini_redis/expiration/cleanup.py`

- 1차 목표는 optional 처리한다.
- 구조만 먼저 만들고, 주기적으로 store를 순회하며 만료 키를 제거하는 background cleanup 루프를 붙일 수 있게 둔다.
- MVP에서는 lazy expiration이 우선이며, cleanup loop는 나중에 연결해도 동작에 영향이 없도록 분리한다.

### `mini_redis/tests/test_ttl.py`

- TTL 단위 테스트를 집중 배치한다.
- 시간 의존성은 실제 `sleep` 최소화 또는 주입 가능한 `now` 인자로 제어한다.

### `mini_redis/tests/test_integration.py`

- Dispatcher와 Storage가 연결된 상태에서 TTL 시나리오를 검증한다.
- 최소 시나리오:
  - `SET foo bar`
  - `EXPIRE foo 3`
  - `TTL foo`
  - 시간 경과
  - `GET foo -> nil`

## 세부 구현 순서

### 1. 데이터/인터페이스 확정

- `Entry.expire_at` 타입과 의미를 확정한다.
- `Storage`가 lazy expiration을 어떤 메서드에서 보장할지 2번과 합의한다.
- TTL 명령 반환값 규약을 숫자 기준으로 고정한다.

### 2. ExpirationManager 구현

- 시각 계산과 TTL 관련 순수 로직을 먼저 구현한다.
- 시간이 필요한 함수는 `now` 주입 가능하게 만들어 테스트를 쉽게 한다.

### 3. Storage에 lazy expiration 연결

- 읽기 시점에 만료 검사를 수행한다.
- 만료된 키는 자동 삭제 후 없는 키처럼 취급한다.

### 4. TTL 명령 구현

- `EXPIRE`, `TTL`, `PERSIST` 명령을 `core/commands/ttl.py`에 구현한다.
- Dispatcher에 연결한다.

### 5. 테스트 추가

- manager 단위 테스트
- storage + ttl 명령 테스트
- end-to-end TTL 흐름 테스트

### 6. Optional cleanup 구조화

- background cleanup loop 초안만 추가한다.
- 서버와의 실제 연결은 추후 진행 가능하도록 분리한다.

## 협업 포인트

### 2번과 맞출 부분

- `Storage` 공개 메서드 목록
- `Entry` 정의 위치와 필드명
- 명령 핸들러가 직접 store를 만질지, storage 메서드만 쓸지
- 에러 메시지 형식

### 1번과 맞출 부분

- TTL 명령의 최종 RESP 응답 형태
- 잘못된 인자 수 / 잘못된 숫자 입력 시 에러 직렬화 방식

### 4번과 맞출 부분

- snapshot 저장 시 `expire_at` 직렬화 규약
- 만료된 키를 persistence에 저장할지 여부
- 통합 테스트에서 시간 경과를 어떻게 다룰지

## 테스트 계획

- `EXPIRE`가 존재하는 키에 대해 `1`을 반환하는지 확인
- `EXPIRE`가 없는 키에 대해 `0`을 반환하는지 확인
- `TTL`이 없는 키에 대해 `-2`를 반환하는지 확인
- TTL이 없는 기존 키에 대해 `TTL`이 `-1`을 반환하는지 확인
- TTL이 설정된 키에 대해 `TTL`이 남은 초를 반환하는지 확인
- 만료 시점 이후 `GET`이 nil 처리되는지 확인
- 만료 시점 이후 `EXISTS`가 `0`이 되는지 확인
- `PERSIST`가 TTL을 제거하고 이후 `TTL`이 `-1`이 되는지 확인
- 잘못된 인자 수와 잘못된 `seconds` 값이 에러 처리되는지 확인

## 구현 판단 기준

- MVP에서는 lazy expiration이 필수, background cleanup은 선택이다.
- TTL 계산 로직은 가능한 한 `ExpirationManager`에 모아 중복을 줄인다.
- `sleep`에 의존하는 테스트보다 시간 주입 방식 테스트를 우선한다.
- 저장소 구조는 `README.md`의 최종 디렉토리 구조를 그대로 유지한다.

## 바로 구현할 작업 목록

1. `Entry.expire_at` 규약 확정
2. `ExpirationManager` 초안 구현
3. `Storage` lazy expiration 연결
4. `core/commands/ttl.py` 구현
5. `dispatcher.py`에 TTL 명령 등록
6. `tests/test_ttl.py`와 `tests/test_integration.py` 작성
