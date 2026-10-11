"""Vikunja adapter.

Speaks API v2. A root that still ends in ``/api/v1`` is normalized before it
gets here. Filter buckets cannot express "a label contains a date on or before
today" without giving up manual columns, so this adapter reports that derived
buckets are unsupported.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Protocol

import requests

from remindban.buckets import BucketCatalog, BucketRole
from remindban.config import VikunjaSettings
from remindban.errors import KanbanError
from remindban.models import BackendCapabilities, Card, ReminderDraft

_CAPABILITIES = BackendCapabilities(
    derived_buckets=False,
    reason=(
        "Vikunja filter buckets are a fixed set of filters, and turning them on "
        "replaces manual columns. They cannot keep Backlog, In Progress, and Done "
        "while filling Today from labels whose date is today or earlier."
    ),
)
_IDENTIFIER = re.compile(r"[^A-Z0-9]+")


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Perform one API call and return decoded JSON, or None."""


class RequestsTransport:
    """``requests`` session that turns network and HTTP failures into ``KanbanError``."""

    def __init__(self, api_root: str, token: str, session: requests.Session | None = None) -> None:
        self.api_root = api_root.rstrip("/")
        self._token = token
        self._session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._session.request(
                method,
                f"{self.api_root}{path}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
                params=params,
                json=json,
                timeout=30,
            )
        except requests.Timeout as exc:
            raise KanbanError(f"Vikunja timed out during {method} {path}.") from exc
        except requests.ConnectionError as exc:
            raise KanbanError(
                f"Could not reach Vikunja at {self.api_root}. Check vikunja.api_root."
            ) from exc
        if response.status_code >= 400:
            raise self._http_error(method, path, response)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise KanbanError(f"Vikunja returned a non-JSON response for {method} {path}.") from exc

    def _http_error(self, method: str, path: str, response: requests.Response) -> KanbanError:
        if response.status_code in {401, 403}:
            return KanbanError(
                f"Vikunja rejected the API token (HTTP {response.status_code}). "
                "Check vikunja.api_token.",
                status=response.status_code,
            )
        snippet = " ".join((response.text or "").split())
        if self._token:
            snippet = snippet.replace(self._token, "[token]")
        detail = f": {snippet[:300]}" if snippet else ""
        return KanbanError(
            f"Vikunja {method} {path} failed (HTTP {response.status_code}){detail}.",
            status=response.status_code,
        )


class VikunjaClient:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        return self.transport.request(method, path, params=params, json=json)

    def get_all(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            query = dict(params or {})
            query["page"] = page
            query["per_page"] = 100
            payload = self.request("GET", path, params=query)
            batch, total_pages = unwrap_page(payload)
            items.extend(batch)
            if page >= total_pages:
                return items
            page += 1


def unwrap_page(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if isinstance(payload, dict) and "items" in payload:
        total_pages = int(payload.get("total_pages") or 1)
        return list(payload.get("items") or []), max(total_pages, 1)
    if isinstance(payload, list):
        return list(payload), 1
    raise KanbanError("Vikunja returned a list in an unexpected shape.")


class VikunjaBackend:
    """Create and move cards in one Vikunja project."""

    def __init__(
        self,
        *,
        project_title: str,
        settings: VikunjaSettings,
        catalog: BucketCatalog,
        transport: Transport | None = None,
    ) -> None:
        self.project_title = project_title
        self.base_url = settings.base_url.rstrip("/")
        self.catalog = catalog
        self.client = VikunjaClient(
            transport or RequestsTransport(settings.api_root, settings.api_token)
        )
        self.project_id: int | None = None
        self.view_id: int | None = None
        self._buckets: dict[str, dict[str, Any]] = {}
        self._labels: dict[str, int] = {}

    def capabilities(self) -> BackendCapabilities:
        return _CAPABILITIES

    def ensure_layout(self) -> None:
        project = self._find_project()
        if project is None:
            project = self._create_project()
        self.project_id = int(project["id"])
        view = self._ensure_kanban_view()
        self.view_id = int(view["id"])
        self._ensure_buckets()
        self._assign_default_buckets(view)

    def create_reminder(self, draft: ReminderDraft) -> Card:
        self.ensure_layout()
        assert self.project_id is not None
        repeat_after, repeat_mode = draft.repeat.to_vikunja()
        created = self.client.request(
            "POST",
            f"/projects/{self.project_id}/tasks",
            json={
                "title": draft.title.strip(),
                "description": draft.notes,
                "due_date": due_to_api(draft.due),
                "repeat_after": repeat_after,
                "repeat_mode": repeat_mode,
                "bucket_id": self._bucket_id(self.catalog.intake.title),
            },
        )
        task_id = str(created["id"])
        try:
            self.move_card(task_id, self.catalog.intake.title)
        except KanbanError as exc:
            identifier = created.get("identifier") or task_id
            raise KanbanError(
                f"Created {identifier}, but could not file it in {self.catalog.intake.title}: {exc}"
            ) from exc
        labels = _unique_labels((draft.date_label, *draft.labels))
        try:
            for label in labels:
                self.client.request(
                    "POST",
                    f"/tasks/{task_id}/labels",
                    json={"label_id": self._ensure_label(label)},
                )
        except KanbanError as exc:
            identifier = created.get("identifier") or task_id
            raise KanbanError(
                f"Created {identifier}, but could not add its date label: {exc}"
            ) from exc
        created["labels"] = [{"title": label} for label in labels]
        created["buckets"] = [{"title": self.catalog.intake.title}]
        return self.to_card(created)

    def list_cards(self) -> list[Card]:
        self.ensure_layout()
        assert self.project_id is not None
        tasks = self.client.get_all(
            f"/projects/{self.project_id}/tasks",
            params={"expand": "buckets"},
        )
        return [self.to_card(task) for task in tasks]

    def move_card(self, card_id: str, bucket_title: str) -> None:
        self.ensure_layout()
        assert self.project_id is not None and self.view_id is not None
        bucket_id = self._bucket_id(bucket_title)
        self.client.request(
            "PUT",
            f"/projects/{self.project_id}/views/{self.view_id}/buckets/{bucket_id}/tasks",
            json={"task_id": int(card_id)},
        )

    def update_labels(self, card: Card, labels: tuple[str, ...]) -> None:
        self.ensure_layout()
        desired = _unique_labels(labels)
        current = {
            str(item.get("title") or "").casefold(): int(item["id"])
            for item in self.client.get_all(f"/tasks/{card.id}/labels")
            if item.get("id") is not None and item.get("title")
        }
        desired_keys = {label.casefold() for label in desired}
        for title, label_id in current.items():
            # Only the managed YYYY-MM-DD label is replaced. Other labels stay.
            if _is_date_label(title) and title not in desired_keys:
                self.client.request("DELETE", f"/tasks/{card.id}/labels/{label_id}")
        for label in desired:
            if label.casefold() not in current:
                self.client.request(
                    "POST",
                    f"/tasks/{card.id}/labels",
                    json={"label_id": self._ensure_label(label)},
                )

    def to_card(self, task: dict[str, Any]) -> Card:
        buckets = task.get("buckets") or []
        bucket = ""
        if buckets and isinstance(buckets[0], dict):
            bucket = str(buckets[0].get("title") or "")
        labels: list[str] = []
        for label in task.get("labels") or []:
            if isinstance(label, dict) and label.get("title"):
                labels.append(str(label["title"]))
        task_id = task.get("id")
        url = f"{self.base_url}/tasks/{task_id}" if self.base_url and task_id is not None else ""
        return Card(
            id=str(task_id),
            identifier=str(task.get("identifier") or task_id or ""),
            title=str(task.get("title") or ""),
            notes=str(task.get("description") or ""),
            due=date_from_api(task.get("due_date")),
            labels=tuple(labels),
            bucket=bucket,
            done=bool(task.get("done")),
            repeat_after=int(task.get("repeat_after") or 0),
            repeat_mode=int(task.get("repeat_mode") or 0),
            url=url,
        )

    def _find_project(self) -> dict[str, Any] | None:
        wanted = self.project_title.casefold()
        for project in self.client.get_all("/projects"):
            if str(project.get("title") or "").casefold() == wanted:
                return project
        return None

    def _create_project(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.project_title,
            "description": "Reminders managed by RemindBan.",
            "hex_color": "89b4fa",
            "identifier": project_identifier(self.project_title),
        }
        try:
            return self.client.request("POST", "/projects", json=payload)
        except KanbanError as exc:
            if "identifier" not in str(exc).casefold():
                raise
            payload.pop("identifier")
            return self.client.request("POST", "/projects", json=payload)

    def _ensure_kanban_view(self) -> dict[str, Any]:
        assert self.project_id is not None
        views = self.client.get_all(f"/projects/{self.project_id}/views")
        kanban = next((view for view in views if view.get("view_kind") == "kanban"), None)
        if kanban is None:
            return self.client.request(
                "POST",
                f"/projects/{self.project_id}/views",
                json={
                    "title": "Board",
                    "view_kind": "kanban",
                    "bucket_configuration_mode": "manual",
                },
            )
        if kanban.get("bucket_configuration_mode") == "filter":
            raise KanbanError(
                "The Remindban kanban view uses filter buckets. RemindBan needs manual "
                "buckets named Backlog, Today, In Progress, and Done."
            )
        return kanban

    def _ensure_buckets(self) -> None:
        assert self.project_id is not None and self.view_id is not None
        path = f"/projects/{self.project_id}/views/{self.view_id}/buckets"
        existing = self.client.get_all(path)
        self._buckets = {
            str(bucket.get("title") or "").casefold(): bucket for bucket in existing
        }
        for index, spec in enumerate(self.catalog.specs):
            if spec.title.casefold() in self._buckets:
                continue
            created = self.client.request(
                "POST",
                path,
                json={"title": spec.title, "position": (index + 1) * 100},
            )
            self._buckets[spec.title.casefold()] = created

    def _assign_default_buckets(self, view: dict[str, Any]) -> None:
        assert self.project_id is not None and self.view_id is not None
        intake_id = self._bucket_id(self.catalog.intake.title)
        done = self.catalog.find_role(BucketRole.DONE)
        done_id = self._bucket_id(done.title) if done else 0
        if view.get("default_bucket_id") == intake_id and view.get("done_bucket_id") == done_id:
            return
        self.client.request(
            "PATCH",
            f"/projects/{self.project_id}/views/{self.view_id}",
            json={"default_bucket_id": intake_id, "done_bucket_id": done_id},
        )

    def _bucket_id(self, title: str) -> int:
        bucket = self._buckets.get(title.casefold())
        if not bucket:
            names = ", ".join(spec.title for spec in self.catalog.specs)
            raise KanbanError(f"No bucket named {title!r}. RemindBan expected: {names}.")
        return int(bucket["id"])

    def _ensure_label(self, title: str) -> int:
        key = title.casefold()
        cached = self._labels.get(key)
        if cached is not None:
            return cached
        for label in self.client.get_all("/labels", params={"q": title}):
            if str(label.get("title") or "").casefold() == key:
                self._labels[key] = int(label["id"])
                return self._labels[key]
        created = self.client.request(
            "POST",
            "/labels",
            json={"title": title, "hex_color": "e6c15a" if _is_date_label(title) else "89b4fa"},
        )
        self._labels[key] = int(created["id"])
        return self._labels[key]


def project_identifier(title: str) -> str:
    compact = _IDENTIFIER.sub("", title.upper())
    return (compact or "REMINDBAN")[:10]


def due_to_api(value: date) -> str:
    """Noon local time, so the calendar day survives timezone conversion."""

    local = datetime.now().astimezone().tzinfo
    return datetime.combine(value, time(12, 0), tzinfo=local).isoformat(timespec="seconds")


def date_from_api(value: Any) -> date | None:
    if not value or not isinstance(value, str) or value.startswith("0001-"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone().date()


def _unique_labels(labels: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    chosen: list[str] = []
    seen: set[str] = set()
    for label in labels:
        text = str(label).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        chosen.append(text)
    return tuple(chosen)


def _is_date_label(title: str) -> bool:
    try:
        date.fromisoformat(title)
    except ValueError:
        return False
    return True
