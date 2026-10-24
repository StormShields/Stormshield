import json
import zipfile
from pathlib import Path

from fort_myers_pack import FIXTURE_PACK, build_fort_myers_pack

from storm_shield.cache_pack import CachePack
from storm_shield.region import load_region, region_path


def test_the_fort_myers_fixture_pack_is_built_from_todays_region_file() -> None:
    assert FIXTURE_PACK.read_bytes() == build_fort_myers_pack(), (
        "regions/fort-myers/region.json changed: rebuild the fixture pack from node/ with "
        "`uv run python tests/fort_myers_pack.py`"
    )


def test_a_node_installs_the_fort_myers_fixture_pack_and_reads_the_region_from_it(
    tmp_path: Path,
) -> None:
    pack = CachePack(tmp_path)
    pack.install(FIXTURE_PACK.read_bytes())
    region_file = pack.file("region.json")
    assert region_file is not None
    region = load_region(region_file)
    assert region == load_region(region_path("fort-myers"))
    assert pack.manifest is not None and pack.manifest["region"] == "fort-myers"
    assert pack.shelter_ids() == [shelter.id for shelter in region.shelters]


def test_the_fixture_packs_shelters_are_the_ones_the_real_build_writes() -> None:
    region = load_region(region_path("fort-myers"))
    built = [
        shelter.model_dump(exclude={"source"}, exclude_none=True) for shelter in region.shelters
    ]
    with zipfile.ZipFile(FIXTURE_PACK) as archive:
        in_pack = json.loads(archive.read("shelters.json"))
    assert in_pack == json.loads(json.dumps(built))
