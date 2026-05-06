"""增量去重状态存储工具。"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from newsradar.models import RawItem


@dataclass(slots=True)
class IncrementalState:
    """跨天去重索引。"""

    seen_items: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def build_seen_items_path(state_root: Path) -> Path:
    """返回跨天去重索引路径。"""

    return state_root / "seen_items.json"


def load_incremental_state(state_root: Path) -> IncrementalState:
    """从磁盘加载增量状态，不存在时返回空状态。"""

    seen_path = build_seen_items_path(state_root)
    seen_items = _load_seen_items(seen_path)
    return IncrementalState(seen_items=seen_items)


def apply_incremental_filter(items: list[RawItem], state: IncrementalState) -> tuple[list[RawItem], dict[str, int]]:
    """基于历史指纹保留未见过的内容。"""

    filtered_items: list[RawItem] = []
    local_seen = {
        source_name: {
            fingerprint
            for day_items in source_items.values()
            for fingerprint in day_items
        }
        for source_name, source_items in state.seen_items.items()
    }
    dropped_by_history = 0

    for item in items:
        fingerprint = _fingerprint_item(item)
        source_seen = local_seen.setdefault(item.source_name, set())
        if fingerprint in source_seen:
            dropped_by_history += 1
            continue

        filtered_items.append(item)
        source_seen.add(fingerprint)

    return filtered_items, {"dropped_by_history": dropped_by_history}


def build_next_incremental_state(
    previous_state: IncrementalState,
    collected_items: list[RawItem],
    filtered_items: list[RawItem],
    run_date: date,
    seen_retention_days: int = 30,
) -> IncrementalState:
    """基于本次成功运行结果推进按来源分桶的历史指纹。"""

    cutoff = run_date - timedelta(days=seen_retention_days)
    next_seen = {
        source_name: {
            day: list(day_items)
            for day, day_items in source_items.items()
            if _parse_seen_day(day) >= cutoff
        }
        for source_name, source_items in previous_state.seen_items.items()
    }
    day_key = run_date.isoformat()
    for item in collected_items:
        source_items = next_seen.setdefault(item.source_name, {})
        fingerprint = _fingerprint_item(item)
        for existing_day, day_items in list(source_items.items()):
            filtered_day_items = [value for value in day_items if value != fingerprint]
            if filtered_day_items:
                source_items[existing_day] = filtered_day_items
            else:
                del source_items[existing_day]
        day_items = source_items.setdefault(day_key, [])
        day_items.insert(0, fingerprint)

    return IncrementalState(seen_items=next_seen)


def persist_incremental_state(state_root: Path, state: IncrementalState) -> None:
    """把增量状态写回磁盘。"""

    seen_path = build_seen_items_path(state_root)
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_payload = {
        "seen_items": {
            source_name: {
                day: list(day_items)
                for day, day_items in sorted(source_items.items(), reverse=True)
            }
            for source_name, source_items in sorted(state.seen_items.items())
        },
    }
    seen_path.write_text(json.dumps(seen_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_seen_items(path: Path) -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_seen = payload.get("seen_items", {})
    if not isinstance(raw_seen, dict):
        return {}

    if raw_seen and all(isinstance(value, str) for value in raw_seen.values()):
        return {}

    parsed: dict[str, dict[str, list[str]]] = {}
    for source_name, source_items in raw_seen.items():
        if not isinstance(source_name, str) or not source_name:
            continue

        if not isinstance(source_items, dict):
            continue

        if source_items and all(isinstance(value, list) for value in source_items.values()):
            parsed_source_items = {
                day: [fingerprint for fingerprint in day_items if isinstance(fingerprint, str) and fingerprint]
                for day, day_items in source_items.items()
                if isinstance(day, str) and day and isinstance(day_items, list)
            }
            parsed_source_items = {
                day: day_items
                for day, day_items in parsed_source_items.items()
                if day_items
            }
            if parsed_source_items:
                parsed[source_name] = parsed_source_items
            continue

        parsed_source_items: dict[str, list[str]] = {}
        for fingerprint, seen_at in sorted(
            source_items.items(),
            key=lambda item: _sort_legacy_seen_item(item[0], item[1]),
            reverse=True,
        ):
            if not isinstance(fingerprint, str) or not fingerprint or not isinstance(seen_at, str):
                continue
            day_key = _parse_legacy_seen_at(seen_at).date().isoformat()
            parsed_source_items.setdefault(day_key, []).append(fingerprint)
        if parsed_source_items:
            parsed[source_name] = parsed_source_items
    return parsed


def _sort_legacy_seen_item(fingerprint: str, seen_at: str) -> tuple[datetime, str]:
    return _parse_legacy_seen_at(seen_at), fingerprint


def _parse_legacy_seen_at(seen_at: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(seen_at)
    except ValueError:
        return datetime.min
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _parse_seen_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def _fingerprint_item(item: RawItem) -> str:
    normalized_url = _normalize_url(item.url)
    if normalized_url:
        return f"url:{normalized_url}"

    normalized_title = " ".join(item.title.split()).strip().lower()
    return f"title:{item.source_name}:{normalized_title}"


def _normalize_url(url: str) -> str:
    if not isinstance(url, str):
        return ""

    stripped = url.strip()
    if not stripped:
        return ""

    parts = urlsplit(stripped)
    path = parts.path.rstrip("/") or parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
