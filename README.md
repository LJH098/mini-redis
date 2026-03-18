# 개요

RESP 프로토콜 기반의 Redis-like 서버를 Python으로 구현한 프로젝트입니다.  
TCP 서버, RESP 파싱/직렬화, 인메모리 저장소, TTL, snapshot persistence를 직접 구성했고, MongoDB와의 조회 속도 비교를 보여주는 웹 데모도 함께 포함되어 있습니다.

## Mini Redis

클라이언트 요청은 `TcpServer -> Session -> RESP Parser -> Command Dispatcher -> Storage` 순서로 처리됩니다. 데이터는 메모리에 저장되고, TTL은 접근 시 lazy expiration과 주기적 cleanup으로 관리됩니다. 또 `Snapshot Manager`가 상태를 `snapshot.json`에 저장해서 재시작 시 복원할 수 있습니다.

## 핵심 포인트

- `selectors` 기반 단일 이벤트 루프로 여러 TCP 연결을 처리합니다.
- RESP 요청을 직접 파싱하고 RESP 응답을 직접 직렬화합니다.
- 데이터는 인메모리 `Storage`에 저장됩니다.
- `EXPIRE`, `TTL`, `PERSIST`를 지원하고 lazy expiration + periodic cleanup을 사용합니다.
- `Snapshot Manager`가 `data/snapshot.json`에 상태를 저장하고 시작 시 복원합니다.
- 웹 데모에서 `MongoDB`와 `mini redis` 조회 흐름을 비교할 수 있습니다.

## Mini Redis 아키텍처

```text
Client
  -> TcpServer
  -> Session
  -> RESP Parser
  -> Command Dispatcher
  -> Command Handlers
  -> Storage

Background
  -> Expiration Manager
  -> Maintenance Step
  -> Snapshot Manager
  -> data/snapshot.json
```

<img width="1536" height="1024" alt="ChatGPT Image 2026년 3월 18일 오후 09_10_40" src="https://github.com/user-attachments/assets/408a4809-a01a-431d-aa6f-b81b064181b9" />


## 요청 처리 흐름

1. 클라이언트가 `6379`로 TCP 연결을 맺습니다.
2. `TcpServer`가 연결을 accept하고 소켓별 `Session`을 등록합니다.
3. `Session`이 입력 바이트를 `in_buffer`에 모읍니다.
4. `RESP Parser`가 요청을 `["GET", "key"]` 같은 명령 배열로 변환합니다.
5. `Command Dispatcher`가 명령 이름에 맞는 핸들러로 분기합니다.
6. 핸들러가 `Storage`를 읽거나 갱신합니다.
7. 결과를 RESP 응답으로 직렬화해 `out_buffer`에 넣습니다.
8. 소켓 write 이벤트 시 클라이언트로 응답을 보냅니다.

## 중점 포인트
1. 동시성 문제가 발생하지 않도록 하려면 어떤 아키텍처 또는 구조를 가져야 할지 고민해 봅니다.

핵심 선택은 단일 selector 이벤트 루프입니다.
TcpServer 하나가 여러 클라이언트 연결을 accept/read/write 이벤트로 처리하고, 요청 처리는 한 이벤트 루프 스레드 안에서 순차적으로 진행됩니다.
그래서 여러 worker thread가 같은 저장소를 동시에 수정하는 구조가 아니고, Storage도 사실상 그 이벤트 루프가 소유하는 lock-free 구조입니다.
> 즉 “락으로 막는 방식”보다 “애초에 동시에 같은 상태를 건드리지 않는 구조”를 택했습니다.

- 관련 코드: mini_redis/server/tcp_server.py, mini_redis/core/storage.py

2. 보관 기간이 만료된 값을 요청받았을 때, 이를 어떻게 처리할지 방안을 마련합니다.

lazy expiration을 적용했습니다.
GET, EXISTS, TTL처럼 key에 접근할 때 먼저 만료 여부를 확인하고, 이미 만료됐다면 그 순간 Storage에서 제거합니다.
여기에 더해 이벤트 루프의 maintenance step이 주기적으로 전체 key를 sweep해서 expired key를 정리합니다.

> 즉 “접근 시 정리 + 주기적 cleanup”을 같이 사용합니다.

- 관련 코드: mini_redis/core/storage.py, mini_redis/core/commands/ttl.py, mini_redis/main.py

3. 외부에서 쉽게 쓰도록 어떤 API 구조를 잡았나

HTTP API가 아니라 RESP over TCP 구조를 택했습니다.
> 즉 Redis와 비슷한 방식으로 6379 포트에 TCP로 붙고, 요청/응답은 RESP 프로토콜을 사용합니다.

이 방식 덕분에 redis-cli 같은 도구나 custom TCP client로 바로 테스트할 수 있습니다.
또 서버 바인딩 주소와 포트도 환경변수로 조정 가능하게 해서 EC2 같은 외부 환경에서도 붙기 쉽게 했습니다.
우리 웹 데모도 내부적으로 이 mini redis에 TCP로 붙는 방식입니다.

- 관련 코드: mini_redis/protocol/parser.py, mini_redis/protocol/serializer.py, mini_redis/config.py, web_app/mini_redis_client.py

4. 저장된 데이터를 무효화하는 방식은 어떻게 했나

무효화는 여러 방법으로 지원합니다.
즉시 삭제:
DEL: 특정 key 삭제
FLUSHALL: 전체 key 삭제
시간 기반 무효화:
EXPIRE: key에 TTL 부여
PERSIST: TTL 제거
> 그래서 사용자는 “즉시 무효화”와 “시간 기반 무효화”를 모두 쓸 수 있습니다.

관련 코드: mini_redis/core/commands/basic.py, mini_redis/core/commands/ttl.py

5. 서버가 다운돼도 데이터를 최대한 안전하게 유지하려면 어떻게 했나

현재는 snapshot persistence 방식을 적용했습니다.
> 시작할 때 data/snapshot.json을 읽어서 메모리 상태를 복원하고, 실행 중에는 주기적으로 snapshot을 저장하며, 종료 시에도 마지막으로 한 번 더 저장합니다.

- 관련 코드: mini_redis/persistence/snapshot.py, mini_redis/main.py

## TTL / Persistence

### TTL

- `expire_at` 기반으로 만료를 관리합니다.
- key 접근 시점에 만료 여부를 확인하는 lazy expiration을 사용합니다.
- 이벤트 루프 tick마다 expired key를 sweep하는 cleanup step도 함께 수행합니다.

### Persistence

- 시작 시 `data/snapshot.json`을 읽어 메모리 상태를 복원합니다.
- 주기적으로 snapshot을 저장합니다.
- 종료 시 마지막으로 한 번 더 저장합니다.
- 임시 파일에 기록한 뒤 `os.replace()`로 교체하는 atomic write를 사용합니다.

## 지원 명령어

- `PING`
- `SET key value`
- `GET key`
- `DEL key [key ...]`
- `EXISTS key [key ...]`
- `INCR key`
- `FLUSHALL`
- `EXPIRE key seconds`
- `TTL key`
- `PERSIST key`

## 협업 / 설계 분담

이 프로젝트는 4명이 병렬로 작업할 수 있도록 계층 단위로 역할을 나눠 설계했습니다.

| 역할 | 담당자 | 담당 영역 | 핵심 책임 |
|---|---|---|---|
| 1번 | `@whiskend` (이경근) | 네트워크 / RESP | TCP 서버, 세션 처리, RESP 파서/직렬화 |
| 2번 | `@Wish-Upon-A-Star` (이원재) | 코어 / 저장소 | Storage, Dispatcher, 기본 명령 처리 |
| 3번 | `@kkm0412` (김규민) | TTL / 만료 | Expiration 정책, `EXPIRE` / `TTL` / `PERSIST`, cleanup |
| 4번 | `@LJH098` (이진혁) | Persistence / 배포 / 테스트 | Snapshot, 웹 데모, Docker Compose, 통합 테스트 |
### 역할별 요약

#### 1번: 네트워크 / RESP

- TCP 연결 수락
- 소켓별 session 관리
- RESP 요청 파싱
- RESP 응답 직렬화

#### 2번: 코어 / 저장소

- 인메모리 key-value 저장소 구현
- `PING`, `SET`, `GET`, `DEL`, `EXISTS`, `INCR`
- Command Dispatcher 구현

#### 3번: TTL / 만료

- `EXPIRE`, `TTL`, `PERSIST`
- lazy expiration
- periodic cleanup

#### 4번: Persistence / 배포 / 테스트

- snapshot save / restore
- `docker compose` 기반 웹 데모 구성
- MongoDB 비교 기능
- 통합 테스트 및 실행 환경 정리

## 주요 디렉터리

```text
mini_redis/
  core/
  expiration/
  persistence/
  protocol/
  server/
  main.py

web_app/
  public/
  main.py

tests/
docker-compose.yml
deploy/mini-redis.service
```

## 실행 방법

### 1. mini redis 실행

기본적으로 `0.0.0.0:6379`에 바인딩됩니다.

```bash
python3 -m mini_redis.main
```

환경변수로 주소와 포트를 덮어쓸 수도 있습니다.

```bash
MINI_REDIS_HOST=0.0.0.0 MINI_REDIS_PORT=6379 python3 -m mini_redis.main
```

### 2. 웹 데모 실행

웹 데모는 FastAPI + MongoDB로 구성되어 있고, mini redis는 별도로 수동 실행합니다.

```bash
docker compose up --build
```

접속 주소:

- `http://localhost:8000`

## 웹 데모 구성

- 좋아요 버튼을 먼저 `10`번 누른 사람이 이기는 게임
- 같은 프로필 데이터를 `MongoDB`와 `mini redis`에서 읽고 속도를 비교하는 데모

구성:

- `mini redis`: 수동 실행
- `web`: FastAPI 서버 + 정적 프론트엔드
- `mongo`: MongoDB

<img width="1695" height="451" alt="image" src="https://github.com/user-attachments/assets/6aac3577-a188-4a24-943f-826b92129628" />



## 테스트

```bash
python3 -m pytest -q
```

## 부하테스트

간단한 부하테스트 스크립트는 [scripts/load_test.py](/Users/jinhyuk/krafton/mini-redis/scripts/load_test.py) 에 있습니다.
EC2 복붙용 실행 가이드와 발표 표 템플릿은 [docs/load-test-runbook.md](/Users/jinhyuk/krafton/mini-redis/docs/load-test-runbook.md) 에 정리했습니다.

mini redis를 실행한 뒤 아래처럼 사용할 수 있습니다.

```bash
python3 -m mini_redis.main
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode ping --workers 50 --requests 10000
```

예시:

```bash
python3 scripts/load_test.py --mode ping --workers 50 --requests 10000
python3 scripts/load_test.py --mode get --workers 50 --requests 10000 --keyspace 200
python3 scripts/load_test.py --mode set --workers 20 --requests 5000 --payload-size 128
python3 scripts/load_test.py --mode incr --workers 20 --requests 5000
python3 scripts/load_test.py --mode mixed --workers 30 --requests 8000
```

출력 항목:

- `throughput`: 초당 처리 요청 수
- `latency avg`: 평균 응답 시간
- `latency median`: 중앙값
- `latency p95 / p99`: 상위 지연 구간
- `latency best / worst`: 최소 / 최대 응답 시간

### EC2 측정 결과

EC2에서 실제로 측정한 결과는 아래와 같습니다.

| 시나리오 | workers | requests | throughput (req/s) | avg (ms) | median (ms) | p95 (ms) | p99 (ms) | errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PING | 50 | 10000 | 11905.73 | 3.996 | 2.804 | 12.308 | 17.031 | 0 |
| GET | 50 | 10000 | 15795.39 | 3.119 | 3.091 | 3.314 | 3.845 | 0 |
| MIXED | 30 | 8000 | 8536.14 | 3.489 | 3.522 | 3.678 | 3.842 | 0 |

요약:

- `GET` 시나리오에서 가장 높은 처리량을 보였습니다.
- `MIXED` 시나리오에서도 `8.5K req/s` 수준으로 안정적으로 동작했습니다.
- 세 시나리오 모두 `errors = 0`으로 측정되었습니다.

## 핵심

이 프로젝트의 핵심은 Redis와 비슷한 서버를 직접 구현하면서, 네트워크 처리, 프로토콜, 저장소, TTL, persistence를 각각 분리된 계층으로 설계했다는 점입니다.
