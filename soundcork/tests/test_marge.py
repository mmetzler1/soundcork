"""Unit tests for the marge XML a speaker receives."""

import xml.etree.ElementTree as ET

from soundcork.constants import DEFAULT_DATESTR
from soundcork.marge import all_sources_xml, presets_xml, recents_xml
from soundcork.model import ConfiguredSource, Preset, Recent

ACCOUNT = "12345"
DEVICE = "abcdefabcdef"


def configured_sources() -> list[ConfiguredSource]:
    return [
        ConfiguredSource(
            display_name="",
            id="100004",
            secret="",
            secret_type="token",
            source_key_type="LOCAL_INTERNET_RADIO",
            source_key_account="",
            created_on=DEFAULT_DATESTR,
            updated_on=DEFAULT_DATESTR,
        ),
        ConfiguredSource(
            display_name="Radio Browser",
            id="100009",
            secret="",
            secret_type="",
            source_key_type="RADIO_BROWSER",
            source_key_account="",
            created_on=DEFAULT_DATESTR,
            updated_on=DEFAULT_DATESTR,
        ),
    ]


class FakeDatastore:
    def __init__(self, presets=None, recents=None):
        self._presets = presets or []
        self._recents = recents or []

    def get_configured_sources(self, account, device=""):
        return configured_sources()

    def get_presets(self, account):
        return list(self._presets)

    def get_recents(self, account, device):
        return list(self._recents)


def radio_preset(preset_id: str, source: str) -> Preset:
    return Preset(
        id=preset_id,
        name=f"Station {preset_id}",
        source=source,
        type="stationurl",
        location="http://soundcork/orion/station?data=x",
        source_account="",
        created_on="1700000000",
        updated_on="1700000000",
        container_art="",
    )


def test_presets_xml_omits_dashboard_only_presets():
    datastore = FakeDatastore(
        presets=[
            radio_preset("2", "LOCAL_INTERNET_RADIO"),
            radio_preset("100", "RADIO_BROWSER"),
        ]
    )

    presets = presets_xml(datastore, ACCOUNT, DEVICE)  # type: ignore[arg-type]

    buttons = [preset.attrib["buttonNumber"] for preset in presets]
    assert buttons == ["2"]


def test_presets_xml_omits_presets_above_the_station_buttons():
    """A speaker has six buttons; ids at or above 100 are soundcork's own."""
    datastore = FakeDatastore(
        presets=[radio_preset("100", "LOCAL_INTERNET_RADIO")],
    )

    presets = presets_xml(datastore, ACCOUNT, DEVICE)  # type: ignore[arg-type]

    assert list(presets) == []


def test_all_sources_xml_omits_sources_the_firmware_does_not_know():
    sources = all_sources_xml(configured_sources())

    ids = [source.attrib["id"] for source in sources]
    assert ids == ["100004"]


def test_recents_xml_omits_internal_sources():
    recent = Recent(
        id="1",
        name="Station",
        source="RADIO_BROWSER",
        type="stationurl",
        location="http://example.com/stream",
        source_account="",
        device_id=DEVICE,
        utc_time="1700000000",
        created_on="1700000000",
    )
    datastore = FakeDatastore(recents=[recent])

    recents = recents_xml(datastore, ACCOUNT, DEVICE)  # type: ignore[arg-type]

    assert list(recents) == []


def test_presets_xml_keeps_a_speaker_preset_intact():
    datastore = FakeDatastore(presets=[radio_preset("3", "LOCAL_INTERNET_RADIO")])

    presets = presets_xml(datastore, ACCOUNT, DEVICE)  # type: ignore[arg-type]

    preset = presets[0]
    assert preset.findtext("name") == "Station 3"
    assert preset.findtext("location") == "http://soundcork/orion/station?data=x"
    source = preset.find("source")
    assert source is not None
    assert source.attrib["id"] == "100004"
    assert isinstance(ET.tostring(presets), bytes)
