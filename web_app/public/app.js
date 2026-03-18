const healthText = document.getElementById("health-text");
const scoreLeft = document.getElementById("score-left");
const scoreRight = document.getElementById("score-right");
const winnerBanner = document.getElementById("winner-banner");
const mongoMs = document.getElementById("mongo-ms");
const redisMs = document.getElementById("redis-ms");
const fasterText = document.getElementById("faster-text");
const mongoPayload = document.getElementById("mongo-payload");
const redisPayload = document.getElementById("redis-payload");

async function requestJson(url, options) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderGame(state) {
  const left = state.players.find((player) => player.id === "left");
  const right = state.players.find((player) => player.id === "right");
  scoreLeft.textContent = left.score;
  scoreRight.textContent = right.score;
  if (state.winner) {
    winnerBanner.textContent = `${state.winner === "left" ? "Player A" : "Player B"} wins at ${state.target} likes.`;
  } else {
    winnerBanner.textContent = `먼저 ${state.target}번 누른 사람이 승리합니다.`;
  }
}

async function loadHealth() {
  const data = await requestJson("/api/health");
  healthText.textContent = data.ok
    ? "MongoDB + mini redis 연결 완료"
    : `상태 확인 필요 (mongo: ${data.mongo}, redis: ${data.miniRedis})`;
}

async function loadGame() {
  const state = await requestJson("/api/game/state");
  renderGame(state);
}

async function clickPlayer(player) {
  const state = await requestJson("/api/game/click", {
    method: "POST",
    body: JSON.stringify({ player }),
  });
  renderGame(state);
}

async function resetGame() {
  const state = await requestJson("/api/game/reset", {
    method: "POST",
    body: JSON.stringify({ keep_history: false }),
  });
  renderGame(state);
}

async function measureLatency() {
  const data = await requestJson("/api/compare/profile");
  mongoMs.textContent = `${data.mongoMs} ms`;
  redisMs.textContent = `${data.redisMs} ms`;
  fasterText.textContent = `${data.faster}가 더 빨랐습니다. 같은 프로필을 두 저장소에서 읽어 비교했습니다.`;
  mongoPayload.textContent = JSON.stringify(data.mongoProfile, null, 2);
  redisPayload.textContent = JSON.stringify(data.redisProfile, null, 2);
}

document.querySelectorAll("[data-player]").forEach((button) => {
  button.addEventListener("click", () => clickPlayer(button.dataset.player));
});

document.getElementById("reset-btn").addEventListener("click", resetGame);
document.getElementById("measure-btn").addEventListener("click", measureLatency);

Promise.all([loadHealth(), loadGame()]).catch((error) => {
  healthText.textContent = `초기화 실패: ${error.message}`;
});
