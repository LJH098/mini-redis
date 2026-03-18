# Mini Redis Load Test Runbook

EC2에서 mini redis에 부하테스트를 걸고, 발표 자료에 넣을 결과를 정리할 때 쓰는 실행 가이드입니다.

## 1. 서버 실행 확인

먼저 mini redis가 실행 중인지 확인합니다.

```bash
ps -ef | grep mini_redis.main
ss -ltnp | grep 6379
```

정상이라면 `6379`가 LISTEN 상태로 보여야 합니다.

## 2. 코드 최신화

```bash
cd ~/mini-redis
git pull
```

## 3. 기본 부하테스트 명령 세트

### PING 처리량

```bash
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode ping --workers 50 --requests 10000
```

### GET 읽기 성능

```bash
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode get --workers 50 --requests 10000 --keyspace 200
```

### SET 쓰기 성능

```bash
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode set --workers 20 --requests 5000 --payload-size 128
```

### INCR 카운터 성능

```bash
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode incr --workers 20 --requests 5000
```

### Mixed 워크로드

```bash
python3 scripts/load_test.py --host 127.0.0.1 --port 6379 --mode mixed --workers 30 --requests 8000
```

## 4. 발표용 추천 시나리오

발표에서는 보통 아래 3개만 돌려도 충분합니다.

1. `PING`
   순수 네트워크 + RESP 처리량 확인
2. `GET`
   메모리 읽기 성능 확인
3. `MIXED`
   실제 서비스에 가까운 혼합 부하 확인

추천 명령:

```bash
python3 scripts/load_test.py --mode ping --workers 50 --requests 10000
python3 scripts/load_test.py --mode get --workers 50 --requests 10000 --keyspace 200
python3 scripts/load_test.py --mode mixed --workers 30 --requests 8000
```

## 5. 결과 해석

- `throughput`
  초당 처리 요청 수입니다. 높을수록 좋습니다.
- `latency avg`
  전체 평균 응답 시간입니다.
- `latency median`
  중앙값입니다. 일반적인 체감 성능을 보기 좋습니다.
- `latency p95`
  상위 5% 느린 요청의 경계값입니다.
- `latency p99`
  상위 1% 느린 요청의 경계값입니다.
- `latency best / worst`
  최소 / 최대 응답 시간입니다.

발표에서는 보통 `throughput`, `avg`, `p95`만 강조해도 충분합니다.

## 6. 결과 표 템플릿

슬라이드에 바로 붙일 수 있는 표 예시는 아래와 같습니다.

| 시나리오 | workers | requests | throughput (req/s) | avg (ms) | p95 (ms) | 비고 |
|---|---:|---:|---:|---:|---:|---|
| PING | 50 | 10000 |  |  |  | 순수 프로토콜 처리 |
| GET | 50 | 10000 |  |  |  | 메모리 읽기 |
| MIXED | 30 | 8000 |  |  |  | 실제 서비스 유사 |

## 7. 발표 멘트 예시

“mini redis에 대해 PING, GET, MIXED 세 가지 부하를 걸어봤습니다. 단일 이벤트 루프 기반 구조이기 때문에 요청 처리 경로가 단순하고, 인메모리 저장소를 사용해서 읽기 요청에서 안정적인 지연 시간을 확인할 수 있었습니다. 발표에서는 throughput과 p95 latency를 중심으로 성능을 비교했습니다.”

## 8. 주의사항

- 테스트 전에 웹 데모가 동시에 같은 mini redis를 강하게 사용하고 있지 않은지 확인합니다.
- snapshot 저장 타이밍과 겹치면 지연이 약간 튈 수 있습니다.
- EC2 인스턴스 타입, 백그라운드 프로세스, 네트워크 상황에 따라 수치는 달라질 수 있습니다.
