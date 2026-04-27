"""
Local JSON-file database — drop-in replacement for Firestore when running locally.
Provides the same collection/document interface so all routers work unchanged.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading


class _JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


class LocalDocument:
    """Mimics a Firestore DocumentSnapshot."""
    def __init__(self, data: Optional[dict], doc_id: str):
        self._data = data
        self.id = doc_id
        self.exists = data is not None

    def to_dict(self):
        return self._data if self._data else {}


class LocalDocumentRef:
    """Mimics a Firestore DocumentReference."""
    def __init__(self, collection_ref, doc_id: str):
        self._collection = collection_ref
        self._id = doc_id

    def get(self) -> LocalDocument:
        data = self._collection._data.get(self._id)
        return LocalDocument(data, self._id)

    def set(self, data: dict):
        self._collection._data[self._id] = data
        self._collection._save()

    def update(self, updates: dict):
        if self._id not in self._collection._data:
            self._collection._data[self._id] = {}
        doc = self._collection._data[self._id]
        for key, value in updates.items():
            if "." in key:
                parts = key.split(".")
                curr = doc
                for p in parts[:-1]:
                    if p not in curr or not isinstance(curr[p], dict):
                        curr[p] = {}
                    curr = curr[p]
                curr[parts[-1]] = value
            else:
                doc[key] = value
        self._collection._save()

    def delete(self):
        if self._id in self._collection._data:
            del self._collection._data[self._id]
            self._collection._save()


class LocalQuery:
    """Mimics a Firestore Query with basic where/order_by/limit."""
    def __init__(self, collection_ref, filters=None, order=None, direction=None):
        self._collection = collection_ref
        self._filters = filters or []
        self._order = order
        self._direction = direction

    def where(self, field, op, value):
        new_filters = self._filters + [(field, op, value)]
        q = LocalQuery(self._collection, new_filters, self._order, self._direction)
        return q

    def order_by(self, field, direction="ASCENDING"):
        q = LocalQuery(self._collection, self._filters, field, direction)
        return q

    def limit(self, n):
        return self  # simplified

    def stream(self):
        results = []
        for doc_id, data in self._collection._data.items():
            match = True
            for field, op, value in self._filters:
                doc_val = _get_nested(data, field)
                if op == "==":
                    if doc_val != value:
                        match = False
                elif op == ">=":
                    if doc_val is None or doc_val < value:
                        match = False
                elif op == "<=":
                    if doc_val is None or doc_val > value:
                        match = False
                elif op == ">":
                    if doc_val is None or doc_val <= value:
                        match = False
                elif op == "<":
                    if doc_val is None or doc_val >= value:
                        match = False
            if match:
                results.append(LocalDocument(data, doc_id))

        if self._order:
            reverse = self._direction in ("DESCENDING", "descending")
            results.sort(
                key=lambda d: str(d.to_dict().get(self._order, "")),
                reverse=reverse
            )
        return results


def _get_nested(data, field):
    """Get a possibly nested field value from a dict."""
    parts = field.split(".")
    val = data
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
    return val


class LocalCollectionRef:
    """Mimics a Firestore CollectionReference."""
    def __init__(self, db, name: str):
        self._db = db
        self._name = name
        self._data = db._load_collection(name)

    def document(self, doc_id: str) -> LocalDocumentRef:
        return LocalDocumentRef(self, doc_id)

    def where(self, field, op, value):
        return LocalQuery(self).where(field, op, value)

    def order_by(self, field, direction="ASCENDING"):
        return LocalQuery(self).order_by(field, direction)

    def stream(self):
        return LocalQuery(self).stream()

    def _save(self):
        self._db._save_collection(self._name, self._data)


class LocalJsonDB:
    """
    Simple JSON-file-backed database that mimics Firestore's interface.
    Each collection is stored as a separate JSON file.
    """
    def __init__(self, data_dir: str = "./local_db"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache = {}

    def collection(self, name: str) -> LocalCollectionRef:
        return LocalCollectionRef(self, name)

    def _load_collection(self, name: str) -> dict:
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            fpath = self._data_dir / f"{name}.json"
            if fpath.exists():
                try:
                    with open(fpath, "r") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            else:
                data = {}
            self._cache[name] = data
            return data

    def _save_collection(self, name: str, data: dict):
        with self._lock:
            self._cache[name] = data
            fpath = self._data_dir / f"{name}.json"
            with open(fpath, "w") as f:
                json.dump(data, f, indent=2, cls=_JsonEncoder)
