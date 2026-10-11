from datetime import date

import pytest
import requests

from remindban.buckets import BucketCatalog
from remindban.config import VikunjaSettings
from remindban.errors import KanbanError
from remindban.models import ReminderDraft, RepeatSpec
from remindban.vikunja import RequestsTransport, VikunjaBackend, date_from_api, due_to_api, project_identifier


class MemoryApi:
    """Just enough of API v2 for the adapter tests."""

    def __init__(self) -> None:
        self.projects: list[dict] = []
        self.views: list[dict] = []
        self.buckets: list[dict] = []
        self.tasks: list[dict] = []
        self.labels: list[dict] = []
        self.task_labels: dict[int, list[int]] = {}
        self.reject_identifier = False
        self.calls: list[tuple] = []
        self._next = 1

    def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, json))
        if path == "/projects" and method == "GET":
            return self._page(self.projects, params)
        if path == "/projects" and method == "POST":
            if self.reject_identifier and json and "identifier" in json:
                self.reject_identifier = False
                raise KanbanError("identifier REMINDBAN is already used")
            project = {"id": self._id(), "views": [], **json}
            self.projects.append(project)
            return project
        if path.endswith("/views") and method == "GET":
            project_id = _ids(path)[0]
            return self._page([view for view in self.views if view["project_id"] == project_id], params)
        if path.endswith("/views") and method == "POST":
            view = {"id": self._id(), "project_id": _ids(path)[0], "default_bucket_id": 0, "done_bucket_id": 0, **json}
            self.views.append(view)
            return view
        if path.endswith("/buckets") and method == "GET":
            view_id = _ids(path)[1]
            return self._page([bucket for bucket in self.buckets if bucket["project_view_id"] == view_id], params)
        if path.endswith("/buckets") and method == "POST":
            bucket = {"id": self._id(), "project_view_id": _ids(path)[1], **json}
            self.buckets.append(bucket)
            return bucket
        if "/views/" in path and method == "PATCH":
            view = self._by_id(self.views, _ids(path)[1])
            view.update(json or {})
            return view
        if path.endswith("/tasks") and method == "POST" and "/buckets/" not in path:
            task = {
                "id": self._id(),
                "identifier": f"REMINDBAN-{len(self.tasks) + 1}",
                "labels": None,
                "buckets": [],
                "done": False,
                **(json or {}),
            }
            self.tasks.append(task)
            return task
        if path.endswith("/tasks") and method == "GET" and "/buckets/" not in path:
            project_id = _ids(path)[0]
            page = [task for task in self.tasks if task.get("project_id", project_id) == project_id]
            for task in page:
                task["buckets"] = [self._by_id(self.buckets, task["bucket_id"])] if task.get("bucket_id") else []
                task["labels"] = [
                    self._by_id(self.labels, label_id) for label_id in self.task_labels.get(task["id"], [])
                ]
            return self._page(page, params)
        if "/buckets/" in path and path.endswith("/tasks") and method == "PUT":
            bucket_id = int(path.split("/buckets/")[1].split("/")[0])
            task = self._by_id(self.tasks, json["task_id"])
            task["bucket_id"] = bucket_id
            task["buckets"] = [self._by_id(self.buckets, bucket_id)]
            return {"task_id": task["id"], "bucket_id": bucket_id}
        if path == "/labels" and method == "GET":
            query = str((params or {}).get("q") or "").casefold()
            matched = [label for label in self.labels if not query or query in label["title"].casefold()]
            return self._page(matched, params)
        if path == "/labels" and method == "POST":
            label = {"id": self._id(), **json}
            self.labels.append(label)
            return label
        if path.endswith("/labels") and method == "POST":
            task_id = _ids(path)[0]
            self.task_labels.setdefault(task_id, []).append(json["label_id"])
            return {"label_id": json["label_id"]}
        if "/labels" in path and method == "GET":
            task_id = _ids(path)[0]
            rows = [self._by_id(self.labels, label_id) for label_id in self.task_labels.get(task_id, [])]
            return self._page(rows, params)
        if "/labels/" in path and method == "DELETE":
            task_id, label_id = _ids(path)
            self.task_labels[task_id] = [
                existing for existing in self.task_labels.get(task_id, []) if existing != label_id
            ]
            return None
        raise AssertionError(f"unexpected {method} {path}")

    def _id(self) -> int:
        value = self._next
        self._next += 1
        return value

    def _page(self, items, params) -> dict:
        page = int((params or {}).get("page") or 1)
        assert page == 1
        return {"items": items, "total_pages": 1, "page": 1}

    def _by_id(self, rows, row_id):
        for row in rows:
            if row["id"] == row_id:
                return row
        raise AssertionError(f"missing id {row_id}")


def _ids(path: str) -> list[int]:
    return [int(part) for part in path.split("/") if part.isdigit()]


def backend(api: MemoryApi | None = None) -> tuple[VikunjaBackend, MemoryApi]:
    api = api or MemoryApi()
    settings = VikunjaSettings("http://127.0.0.1:3456/api/v2", "https://v.tyler.cloud", "secret")
    return (
        VikunjaBackend(
            project_title="Remindban",
            settings=settings,
            catalog=BucketCatalog.defaults(),
            transport=api,
        ),
        api,
    )


def test_identifier_and_due_date_helpers():
    assert project_identifier("Remindban") == "REMINDBAN"
    assert date_from_api("0001-01-01T00:00:00Z") is None
    assert date_from_api(due_to_api(date(2026, 10, 12))) == date(2026, 10, 12)


def test_ensure_layout_creates_project_and_manual_buckets():
    store = MemoryApi()
    client, api = backend(store)
    client.ensure_layout()
    assert api.projects[0]["title"] == "Remindban"
    assert api.projects[0]["identifier"] == "REMINDBAN"
    assert [bucket["title"] for bucket in api.buckets] == [
        "Backlog",
        "Today",
        "In Progress",
        "Done",
    ]
    assert api.views[0]["default_bucket_id"] == api.buckets[0]["id"]
    assert api.views[0]["done_bucket_id"] == api.buckets[3]["id"]
    assert client.capabilities().derived_buckets is False

    client.ensure_layout()
    assert len(api.projects) == 1
    assert len(api.buckets) == 4


def test_create_retries_without_a_taken_identifier_and_files_the_date_label():
    store = MemoryApi()
    store.reject_identifier = True
    client, api = backend(store)
    created = client.create_reminder(
        ReminderDraft(
            title="Call mom",
            due=date(2026, 10, 12),
            repeat=RepeatSpec.monthly(),
            notes="Sunday",
            labels=("home",),
        )
    )
    assert created.bucket == "Backlog"
    assert created.labels == ("2026-10-12", "home")
    assert created.identifier == "REMINDBAN-1"
    task = api.tasks[0]
    assert task["repeat_mode"] == 1
    assert task["repeat_after"] == 0
    assert task["description"] == "Sunday"
    assert task["bucket_id"] == api.buckets[0]["id"]
    assert api.projects[0].get("identifier") is None
    assert [label["title"] for label in api.labels] == ["2026-10-12", "home"]


def test_filter_buckets_are_refused():
    store = MemoryApi()
    project = {"id": store._id(), "title": "Remindban"}
    store.projects.append(project)
    store.views.append(
        {
            "id": store._id(),
            "project_id": project["id"],
            "view_kind": "kanban",
            "bucket_configuration_mode": "filter",
        }
    )
    client, _api = backend(store)
    with pytest.raises(KanbanError, match="manual"):
        client.ensure_layout()


def test_http_errors_do_not_include_the_token():
    class Response:
        status_code = 500
        text = "token super-secret leaked"
        content = b"token super-secret leaked"

        def json(self):
            return {}

    class Session:
        def request(self, *args, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer super-secret"
            return Response()

    transport = RequestsTransport("http://example.test/api/v2", "super-secret", session=Session())
    with pytest.raises(KanbanError, match="HTTP 500") as caught:
        transport.request("GET", "/projects")
    assert "super-secret" not in str(caught.value)

    class Denied(Response):
        status_code = 401
        text = ""
        content = b""

    class DeniedSession(Session):
        def request(self, *args, **kwargs):
            return Denied()

    transport = RequestsTransport("http://example.test/api/v2", "super-secret", session=DeniedSession())
    with pytest.raises(KanbanError, match="rejected the API token") as caught:
        transport.request("GET", "/projects")
    assert "super-secret" not in str(caught.value)


def test_connection_errors_name_the_api_root():
    class Session:
        def request(self, *args, **kwargs):
            raise requests.ConnectionError("no route")

    transport = RequestsTransport("http://board.test/api/v2", "secret", session=Session())
    with pytest.raises(KanbanError, match="http://board.test/api/v2"):
        transport.request("GET", "/projects")
