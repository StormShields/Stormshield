from pathlib import Path

from sandbox_app_smoke import bundle_problems


def _bundle(root: Path, regions: tuple[str, ...] = ("nepal", "fort-myers")) -> Path:
    for region in regions:
        pack = root / "_internal" / "node" / "build" / region / "cache-pack.zip"
        pack.parent.mkdir(parents=True)
        pack.write_bytes(b"pack")
    return root


def test_a_download_with_both_packs_and_no_env_file_has_no_problems(tmp_path: Path) -> None:
    assert bundle_problems(_bundle(tmp_path)) == []


def test_an_env_file_anywhere_in_the_download_is_a_problem(tmp_path: Path) -> None:
    _bundle(tmp_path)
    (tmp_path / "_internal" / ".env").write_text("SECRET=1")
    (tmp_path / ".env.production").write_text("SECRET=2")
    (tmp_path / ".env.example").write_text("")

    problems = bundle_problems(tmp_path)

    assert sorted(problems) == [
        ".env.production must not be in the download",
        "_internal/.env must not be in the download",
    ]


def test_a_missing_region_pack_is_a_problem(tmp_path: Path) -> None:
    assert bundle_problems(_bundle(tmp_path, ("nepal",))) == [
        "the fort-myers Cache Pack is not in the download"
    ]
