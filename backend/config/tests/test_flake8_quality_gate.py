from scripts.flake8_quality_gate import (
    PythonFileChange,
    find_regressions,
    parse_changed_python_files,
    parse_flake8_counts,
)


def test_parse_changed_python_files_tracks_add_modify_rename_and_copy():
    raw_diff = (
        b"M\0backend/apps/catalog/models.py\0"
        b"A\0backend/apps/catalog/new_service.py\0"
        b"D\0backend/apps/catalog/old_service.py\0"
        b"R100\0backend/apps/catalog/old.py\0backend/apps/catalog/new.py\0"
        b"C100\0backend/apps/catalog/source.py\0backend/apps/catalog/copy.py\0"
        b"M\0frontend/src/page.tsx\0"
        b"M\0backend/README.md\0"
    )

    assert parse_changed_python_files(raw_diff) == [
        PythonFileChange("apps/catalog/models.py", "apps/catalog/models.py"),
        PythonFileChange("apps/catalog/new_service.py", None),
        PythonFileChange("apps/catalog/new.py", "apps/catalog/old.py"),
        PythonFileChange("apps/catalog/copy.py", None),
    ]


def test_parse_flake8_counts_normalizes_relative_and_absolute_paths(tmp_path):
    output = "\n".join(
        [
            "./apps/catalog/models.py:10:1: F401 unused import",
            "apps/catalog/models.py:12:3: E303 too many blank lines",
            f"{tmp_path}/scripts/check.py:4:1: F821 undefined name",
            "not a diagnostic",
        ]
    )

    assert parse_flake8_counts(output, tmp_path) == {
        "apps/catalog/models.py": 2,
        "scripts/check.py": 1,
    }


def test_find_regressions_allows_equal_or_lower_counts_only():
    changes = [
        PythonFileChange("legacy.py", "legacy.py"),
        PythonFileChange("improved.py", "improved.py"),
        PythonFileChange("new.py", None),
        PythonFileChange("clean.py", None),
    ]

    assert find_regressions(
        changes,
        current_counts={"legacy.py": 4, "improved.py": 2, "new.py": 1},
        base_counts={"legacy.py": 3, "improved.py": 3, "new.py": 0, "clean.py": 0},
    ) == ["legacy.py: 3 -> 4", "new.py: 0 -> 1"]
