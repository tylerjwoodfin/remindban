"""Bucket catalog.

v1 always uses four buckets. The types below are the extension point: a later
release can load a catalog from config without changing sync or the kanban
adapters. ``Today`` is derived from date labels, not typed by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BucketRole(Enum):
    """What a bucket means to RemindBan, independent of the kanban tool."""

    INTAKE = "intake"
    DERIVED = "derived"
    ACTIVE = "active"
    DONE = "done"


@dataclass(frozen=True)
class BucketSpec:
    """One swimlane.

    ``key`` is stable in config and code. ``title`` is the column name written
    to the kanban tool.
    """

    key: str
    title: str
    role: BucketRole

    @property
    def derived(self) -> bool:
        return self.role is BucketRole.DERIVED


DEFAULT_BUCKETS: tuple[BucketSpec, ...] = (
    BucketSpec("backlog", "Backlog", BucketRole.INTAKE),
    BucketSpec("today", "Today", BucketRole.DERIVED),
    BucketSpec("in_progress", "In Progress", BucketRole.ACTIVE),
    BucketSpec("done", "Done", BucketRole.DONE),
)


class BucketCatalog:
    """The buckets RemindBan knows how to create and sync."""

    def __init__(self, specs: tuple[BucketSpec, ...] | list[BucketSpec]) -> None:
        self.specs = tuple(specs)
        self._validate()

    @classmethod
    def defaults(cls) -> BucketCatalog:
        return cls(DEFAULT_BUCKETS)

    def _validate(self) -> None:
        keys = [spec.key for spec in self.specs]
        titles = [spec.title.casefold() for spec in self.specs]
        if len(keys) != len(set(keys)):
            raise ValueError("Bucket keys must be unique.")
        if len(titles) != len(set(titles)):
            raise ValueError("Bucket titles must be unique.")
        self.intake
        self.derived

    def _one(self, role: BucketRole, label: str) -> BucketSpec:
        matches = [spec for spec in self.specs if spec.role is role]
        if len(matches) != 1:
            raise ValueError(f"A bucket catalog needs exactly one {label} bucket.")
        return matches[0]

    @property
    def intake(self) -> BucketSpec:
        return self._one(BucketRole.INTAKE, "intake")

    @property
    def derived(self) -> BucketSpec:
        return self._one(BucketRole.DERIVED, "derived")

    def sticky_titles(self) -> frozenset[str]:
        """Buckets sync must not move cards out of."""

        return frozenset(
            spec.title.casefold()
            for spec in self.specs
            if spec.role in {BucketRole.ACTIVE, BucketRole.DONE}
        )

    def matching(self, title: str) -> BucketSpec | None:
        folded = title.casefold()
        for spec in self.specs:
            if spec.title.casefold() == folded:
                return spec
        return None


def parse_bucket_specs(items: list[dict[str, str]]) -> tuple[BucketSpec, ...]:
    """Parse a future config list. v1 does not call this from ``load_config``."""

    specs: list[BucketSpec] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Bucket {index} must be a mapping.")
        try:
            role = BucketRole(str(item["role"]))
            specs.append(
                BucketSpec(
                    key=str(item["key"]).strip(),
                    title=str(item["title"]).strip(),
                    role=role,
                )
            )
        except KeyError as exc:
            raise ValueError(f"Bucket {index} is missing {exc.args[0]!r}.") from exc
        except ValueError as exc:
            raise ValueError(f"Bucket {index} has an unknown role.") from exc
    return BucketCatalog(specs).specs
