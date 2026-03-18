from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo import MongoClient


@dataclass
class MongoRepository:
    client: MongoClient
    database_name: str

    @property
    def collection(self):
        return self.client[self.database_name]["profiles"]

    def ensure_seed_profile(self, document_id: str) -> dict[str, Any]:
        document = {
            "_id": document_id,
            "name": "Latency Demo User",
            "level": 12,
            "favoriteMode": "tap-race",
            "headline": "MongoDB vs mini redis read benchmark",
        }
        self.collection.update_one(
            {"_id": document_id},
            {"$setOnInsert": document},
            upsert=True,
        )
        return self.get_profile(document_id)

    def get_profile(self, document_id: str) -> dict[str, Any] | None:
        document = self.collection.find_one({"_id": document_id})
        if document is None:
            return None
        document["id"] = document.pop("_id")
        return document
