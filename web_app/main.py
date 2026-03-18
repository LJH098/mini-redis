from __future__ import annotations

import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pymongo import MongoClient

from web_app.config import config
from web_app.mini_redis_client import MiniRedisClient
from web_app.mongo_repository import MongoRepository


class ClickRequest(BaseModel):
    player: str = Field(pattern="^(left|right)$")


class ResetRequest(BaseModel):
    keep_history: bool = False


redis_client = MiniRedisClient(config.mini_redis_host, config.mini_redis_port)
mongo_client = MongoClient(config.mongo_uri)
mongo_repository = MongoRepository(mongo_client, config.mongo_db)
game_lock = threading.Lock()

PLAYER_KEYS = {"left": "game:player:left", "right": "game:player:right"}
WINNER_KEY = "game:winner"
HISTORY_COLLECTION = "match_history"


def _public_dir() -> Path:
    return Path(__file__).resolve().parent / "public"


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    profile = mongo_repository.ensure_seed_profile(config.compare_document_id)
    try:
        redis_client.set(f"profile:{config.compare_document_id}", json.dumps(profile))
    except Exception:
        pass
    yield
    mongo_client.close()


app = FastAPI(title="Mini Redis Demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=_public_dir()), name="static")


@app.get("/")
def index():
    return FileResponse(_public_dir() / "index.html")


@app.get("/api/health")
def health():
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    try:
        mongo_client.admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {"ok": redis_ok and mongo_ok, "mongo": mongo_ok, "miniRedis": redis_ok}


@app.get("/api/game/state")
def game_state():
    return _read_game_state()


@app.post("/api/game/click")
def click_game(request: ClickRequest):
    with game_lock:
        state = _read_game_state()
        if state["winner"] is not None:
            return state

        score = redis_client.incr(PLAYER_KEYS[request.player])
        winner = request.player if score >= config.like_target else None
        if winner is not None:
            redis_client.set(WINNER_KEY, winner)
            mongo_client[config.mongo_db][HISTORY_COLLECTION].insert_one(
                {
                    "winner": winner,
                    "leftScore": int(redis_client.get(PLAYER_KEYS["left"]) or "0"),
                    "rightScore": int(redis_client.get(PLAYER_KEYS["right"]) or "0"),
                    "finishedAt": time.time(),
                }
            )
        return _read_game_state()


@app.post("/api/game/reset")
def reset_game(request: ResetRequest):
    del request
    with game_lock:
        redis_client.delete(PLAYER_KEYS["left"], PLAYER_KEYS["right"], WINNER_KEY)
    return _read_game_state()


@app.get("/api/compare/profile")
def compare_profile():
    document_id = config.compare_document_id

    mongo_start = time.perf_counter()
    mongo_profile = mongo_repository.get_profile(document_id)
    mongo_ms = (time.perf_counter() - mongo_start) * 1000

    redis_start = time.perf_counter()
    cached_profile = redis_client.get(f"profile:{document_id}")
    redis_ms = (time.perf_counter() - redis_start) * 1000

    if mongo_profile is None:
        raise HTTPException(status_code=404, detail="profile not found")

    if cached_profile is None:
        redis_client.set(f"profile:{document_id}", json.dumps(mongo_profile))
        cached_profile = json.dumps(mongo_profile)

    return {
        "documentId": document_id,
        "mongoMs": round(mongo_ms, 3),
        "redisMs": round(redis_ms, 3),
        "faster": "mini redis" if redis_ms < mongo_ms else "mongodb",
        "mongoProfile": mongo_profile,
        "redisProfile": json.loads(cached_profile),
    }


def _read_game_state():
    left_score = int(redis_client.get(PLAYER_KEYS["left"]) or "0")
    right_score = int(redis_client.get(PLAYER_KEYS["right"]) or "0")
    winner = redis_client.get(WINNER_KEY)
    return {
        "target": config.like_target,
        "winner": winner,
        "players": [
            {"id": "left", "label": "Player A", "score": left_score},
            {"id": "right", "label": "Player B", "score": right_score},
        ],
    }
