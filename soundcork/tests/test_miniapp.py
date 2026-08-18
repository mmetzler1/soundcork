from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from soundcork.miniapp import get_miniapp_router
from soundcork.model import Preset

ACCOUNT_ID = "8208423"
DEVICE_ID = "device-1"


class FakeDatastore:
    def account_exists(self, account_id: str) -> bool:
        return account_id == ACCOUNT_ID

    def list_accounts(self) -> list[str]:
        return [ACCOUNT_ID]

    def get_account_info(self, account_id: str) -> str:
        assert account_id == ACCOUNT_ID
        return "Účet ložnice"

    def list_devices(self, account_id: str) -> list[str]:
        assert account_id == ACCOUNT_ID
        return [DEVICE_ID]

    def get_device_info(self, account_id: str, device_id: str):
        assert account_id == ACCOUNT_ID
        assert device_id == DEVICE_ID
        return SimpleNamespace(
            name="ložnice",
            product_code="SoundTouch10",
            device_id=DEVICE_ID,
        )

    def __init__(self) -> None:
        self.saved_presets: list[Preset] | None = None

    def get_presets(self, account_id: str) -> list[Preset]:
        assert account_id == ACCOUNT_ID
        return [
            Preset(
                id="4",
                name="Rádio Proglas",
                source="LOCAL_INTERNET_RADIO",
                type="STORED_MUSIC",
                location="proglas",
                container_art="",
            )
        ]

    def save_presets(self, account_id: str, device_id: str, presets: list[Preset]):
        self.saved_presets = presets


class FakeSpeakers:
    def __init__(self, play_result: bool = True) -> None:
        self.play_result = play_result
        self.play_calls: list[tuple[str, str]] = []
        self.stored_presets: list[tuple[str, int, str, str]] = []
        self.bass = {"available": True, "bass": -3, "min": -9, "max": 0, "default": 0}

    def all_devices(self):
        return {
            DEVICE_ID: SimpleNamespace(
                account=ACCOUNT_ID,
                online=True,
                in_soundcork=True,
                marge_server="Soundcork",
            )
        }

    def play_content_item(self, device_id: str, content_item_id: str) -> bool:
        self.play_calls.append((device_id, content_item_id))
        return self.play_result

    def get_bass(self, device_id: str):
        return self.bass

    def set_bass(self, device_id: str, level: int) -> bool:
        self.bass["bass"] = level
        return True

    def store_radio_station_preset(
        self, device_id: str, slot: int, stream_url: str, name: str
    ) -> str:
        self.stored_presets.append((device_id, slot, stream_url, name))
        return f"http://soundcork/orion/station?data={name}"


def make_client(monkeypatch, speakers: FakeSpeakers | None = None):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    app = FastAPI()
    fake_speakers = speakers or FakeSpeakers()
    fake_datastore = FakeDatastore()
    app.include_router(
        get_miniapp_router(cast(Any, fake_datastore), cast(Any, fake_speakers))
    )
    client = TestClient(app)
    client.datastore = fake_datastore  # type: ignore[attr-defined]
    return client, fake_speakers


SESSION = {
    "Cookie": f"soundcork_account_id={ACCOUNT_ID}; "
    f"soundcork_selected_device_id={DEVICE_ID}"
}


def test_save_hardware_preset_writes_to_speaker_and_datastore(monkeypatch):
    """A station button has to be set on the speaker as well as recorded here.

    Writing only to the datastore would leave the button dead until the
    speaker happens to ask soundcork for its presets again.
    """
    client, speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/save-hardware-preset",
        json={"name": "NDR 2", "url": "http://icecast.ndr.de/stream.mp3", "slot": 3},
        headers=SESSION,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "slot": 3}
    assert speakers.stored_presets == [
        (DEVICE_ID, 3, "http://icecast.ndr.de/stream.mp3", "NDR 2")
    ]
    saved = client.datastore.saved_presets  # type: ignore[attr-defined]
    stored = next(preset for preset in saved if preset.id == "3")
    assert stored.name == "NDR 2"
    assert stored.source == "LOCAL_INTERNET_RADIO"
    assert stored.location == "http://soundcork/orion/station?data=NDR 2"


def test_save_hardware_preset_rejects_a_slot_without_a_button(monkeypatch):
    client, speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/save-hardware-preset",
        json={"name": "NDR 2", "url": "http://example.com/s.mp3", "slot": 7},
        headers=SESSION,
    )

    assert response.status_code == 400
    assert speakers.stored_presets == []


def test_save_hardware_preset_needs_a_selected_device(monkeypatch):
    client, speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/save-hardware-preset",
        json={"name": "NDR 2", "url": "http://example.com/s.mp3", "slot": 1},
        headers={"Cookie": f"soundcork_account_id={ACCOUNT_ID}"},
    )

    assert response.status_code == 400
    assert speakers.stored_presets == []


def test_bass_reports_the_range_the_device_supports(monkeypatch):
    client, _speakers = make_client(monkeypatch)

    response = client.get("/miniapp/bass", headers=SESSION)

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "bass": -3,
        "min": -9,
        "max": 0,
        "default": 0,
    }


def test_bass_can_be_set(monkeypatch):
    client, speakers = make_client(monkeypatch)

    response = client.post("/miniapp/bass", json={"bass": -6}, headers=SESSION)

    assert response.status_code == 200
    assert speakers.bass["bass"] == -6


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def test_select_device_percent_encodes_unicode_cookie(monkeypatch):
    client, _speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/select-device",
        data={"device_id": DEVICE_ID, "device_name": "ložnice"},
        follow_redirects=False,
    )

    cookies = "\n".join(set_cookie_headers(response))
    assert response.status_code == 303
    assert "soundcork_selected_device=lo%C5%BEnice" in cookies
    assert "ložnice" not in cookies


def test_dashboard_decodes_display_cookies(monkeypatch):
    client, _speakers = make_client(monkeypatch)

    response = client.get(
        "/miniapp/dashboard",
        headers={
            "Cookie": (
                f"soundcork_account_id={ACCOUNT_ID}; "
                "soundcork_account_label=%C3%9A%C4%8Det%20lo%C5%BEnice; "
                "soundcork_selected_device=lo%C5%BEnice; "
                "soundcork_selected_content_item_name=R%C3%A1dio%20Proglas; "
                f"soundcork_selected_device_id={DEVICE_ID}"
            )
        },
    )

    assert response.status_code == 200
    assert "Účet ložnice" in response.text
    assert "ložnice" in response.text
    assert "Rádio Proglas" in response.text


def test_select_content_item_plays_when_device_is_selected(monkeypatch):
    client, speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/select-content-item",
        data={"content_item_id": "4", "content_item_name": "Rádio Proglas"},
        headers={"Cookie": f"soundcork_selected_device_id={DEVICE_ID}"},
        follow_redirects=False,
    )

    cookies = "\n".join(set_cookie_headers(response))
    assert response.status_code == 303
    assert speakers.play_calls == [(DEVICE_ID, "4")]
    assert "soundcork_selected_content_item_name=R%C3%A1dio%20Proglas" in cookies
    assert "soundcork_is_playing=true" in cookies


def test_select_content_item_without_device_only_selects(monkeypatch):
    client, speakers = make_client(monkeypatch)

    response = client.post(
        "/miniapp/select-content-item",
        data={"content_item_id": "4", "content_item_name": "Rádio Proglas"},
        follow_redirects=False,
    )

    cookies = "\n".join(set_cookie_headers(response))
    assert response.status_code == 303
    assert speakers.play_calls == []
    assert "soundcork_selected_content_item_name=R%C3%A1dio%20Proglas" in cookies
    assert "soundcork_is_playing" not in cookies


def test_select_content_item_records_failed_playback(monkeypatch):
    client, speakers = make_client(monkeypatch, FakeSpeakers(play_result=False))

    response = client.post(
        "/miniapp/select-content-item",
        data={"content_item_id": "4", "content_item_name": "Rádio Proglas"},
        headers={"Cookie": f"soundcork_selected_device_id={DEVICE_ID}"},
        follow_redirects=False,
    )

    cookies = "\n".join(set_cookie_headers(response))
    assert response.status_code == 303
    assert speakers.play_calls == [(DEVICE_ID, "4")]
    assert "soundcork_is_playing=false" in cookies
