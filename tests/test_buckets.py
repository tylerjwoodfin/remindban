import pytest

from remindban.buckets import BucketCatalog, BucketRole, parse_bucket_specs


def test_defaults_have_one_intake_and_one_derived_bucket():
    catalog = BucketCatalog.defaults()
    assert catalog.intake.title == "Backlog"
    assert catalog.derived.title == "Today"
    assert catalog.derived.derived
    assert catalog.sticky_titles() == {"in progress", "done"}
    assert [spec.role for spec in catalog.specs] == [
        BucketRole.INTAKE,
        BucketRole.DERIVED,
        BucketRole.ACTIVE,
        BucketRole.DONE,
    ]


def test_future_config_shape_can_rename_buckets():
    specs = parse_bucket_specs(
        [
            {"key": "inbox", "title": "Later", "role": "intake"},
            {"key": "today", "title": "Due", "role": "derived"},
            {"key": "doing", "title": "Doing", "role": "active"},
            {"key": "done", "title": "Finished", "role": "done"},
        ]
    )
    catalog = BucketCatalog(specs)
    assert catalog.intake.title == "Later"
    assert catalog.derived.title == "Due"
    assert catalog.matching("doing").title == "Doing"


def test_catalog_rejects_two_derived_buckets():
    with pytest.raises(ValueError, match="exactly one"):
        parse_bucket_specs(
            [
                {"key": "inbox", "title": "Backlog", "role": "intake"},
                {"key": "a", "title": "Today", "role": "derived"},
                {"key": "b", "title": "Also", "role": "derived"},
            ]
        )
