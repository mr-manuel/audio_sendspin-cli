"""Tests for ALSA device listing and resolution in audio_devices.py."""

from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
import sounddevice

import sendspin.audio_devices as _mod
import sendspin.cli as _cli
from sendspin.audio_devices import (
    AudioDevice,
    _parse_hw_format,
    _try_alsa_device,
    list_alsa_devices,
    resolve_audio_device,
)


# ---------------------------------------------------------------------------
# Sample data matching real `sendspin player --list-audio-devices` output
# ---------------------------------------------------------------------------

# PortAudio devices as returned by query_devices() on this system.
# Index 15 ("default") is the default output device.
PORTAUDIO_DEVICES = [
    AudioDevice(
        index=0,
        name="Loopback: PCM (hw:0,0)",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=1,
        name="Loopback: PCM (hw:0,1)",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=2,
        name="ICUSBAUDIO7D: USB Audio (hw:1,0)",
        output_channels=8,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=3,
        name="snd_rpi_hifiberry_dacplus: HiFiBerry DAC+ HiFi pcm512x-hifi-0 (hw:2,0)",
        output_channels=2,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=4,
        name="sysdefault",
        output_channels=128,
        sample_rate=48000.0,
        is_default=False,
    ),
    AudioDevice(
        index=5,
        name="front",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=6,
        name="surround21",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=7,
        name="surround40",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=8,
        name="surround41",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=9,
        name="surround50",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=10,
        name="surround51",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=11,
        name="surround71",
        output_channels=32,
        sample_rate=44100.0,
        is_default=False,
    ),
    AudioDevice(
        index=12,
        name="jsm_dmix_sndrpihifiberry",
        output_channels=2,
        sample_rate=48000.0,
        is_default=False,
    ),
    AudioDevice(
        index=13,
        name="jsm_speaker_left",
        output_channels=128,
        sample_rate=48000.0,
        is_default=False,
    ),
    AudioDevice(
        index=14,
        name="jsm_speaker_right",
        output_channels=128,
        sample_rate=48000.0,
        is_default=False,
    ),
    AudioDevice(
        index=15,
        name="default",
        output_channels=128,
        sample_rate=48000.0,
        is_default=True,
    ),
    AudioDevice(
        index=16,
        name="dmix",
        output_channels=2,
        sample_rate=48000.0,
        is_default=False,
    ),
]

# ALSA devices as returned by list_alsa_devices() (parsed from aplay -L).
ALSA_DEVICES: list[tuple[str, str]] = [
    ("null", "Discard all samples (playback) or generate zero samples (capture)"),
    ("bluealsa", "Bluetooth Audio"),
    ("jsm_dmix_sndrpihifiberry", ""),
    ("jsm_speaker_left", "Speaker Left"),
    ("jsm_speaker_right", "Speaker Right"),
    ("hw:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("hw:CARD=Loopback,DEV=1", "Loopback, Loopback PCM"),
    ("plughw:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("plughw:CARD=Loopback,DEV=1", "Loopback, Loopback PCM"),
    ("default:CARD=Loopback", "Loopback, Loopback PCM"),
    ("sysdefault:CARD=Loopback", "Loopback, Loopback PCM"),
    ("front:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround21:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround40:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround41:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround50:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround51:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("surround71:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("dmix:CARD=Loopback,DEV=0", "Loopback, Loopback PCM"),
    ("dmix:CARD=Loopback,DEV=1", "Loopback, Loopback PCM"),
    ("hw:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("plughw:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("default:CARD=ICUSBAUDIO7D", "ICUSBAUDIO7D, USB Audio"),
    ("sysdefault:CARD=ICUSBAUDIO7D", "ICUSBAUDIO7D, USB Audio"),
    ("front:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround21:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround40:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround41:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround50:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround51:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("surround71:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("iec958:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    ("dmix:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio"),
    (
        "hw:CARD=sndrpihifiberry,DEV=0",
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
    ),
    (
        "plughw:CARD=sndrpihifiberry,DEV=0",
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
    ),
    (
        "default:CARD=sndrpihifiberry",
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
    ),
    (
        "sysdefault:CARD=sndrpihifiberry",
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
    ),
    (
        "dmix:CARD=sndrpihifiberry,DEV=0",
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
    ),
]

# aplay -L raw output corresponding to ALSA_DEVICES above.
APLAY_OUTPUT = """\
null
    Discard all samples (playback) or generate zero samples (capture)
bluealsa
    Bluetooth Audio
jsm_dmix_sndrpihifiberry
jsm_speaker_left
    Speaker Left
jsm_speaker_right
    Speaker Right
hw:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    Direct hardware device without any conversions
hw:CARD=Loopback,DEV=1
    Loopback, Loopback PCM
    Direct hardware device without any conversions
plughw:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    Hardware device with all software conversions
plughw:CARD=Loopback,DEV=1
    Loopback, Loopback PCM
    Hardware device with all software conversions
default:CARD=Loopback
    Loopback, Loopback PCM
    Default Audio Device
sysdefault:CARD=Loopback
    Loopback, Loopback PCM
    Default Audio Device
front:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    Front output / input
surround21:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    2.1 Surround output to Front and Subwoofer speakers
surround40:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    4.0 Surround output to Front and Rear speakers
surround41:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    4.1 Surround output to Front, Rear and Subwoofer speakers
surround50:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    5.0 Surround output to Front, Center and Rear speakers
surround51:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    5.1 Surround output to Front, Center, Rear and Subwoofer speakers
surround71:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    7.1 Surround output to Front, Center, Side, Rear and Woofer speakers
dmix:CARD=Loopback,DEV=0
    Loopback, Loopback PCM
    Direct sample mixing device
dmix:CARD=Loopback,DEV=1
    Loopback, Loopback PCM
    Direct sample mixing device
hw:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    Direct hardware device without any conversions
plughw:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    Hardware device with all software conversions
default:CARD=ICUSBAUDIO7D
    ICUSBAUDIO7D, USB Audio
    Default Audio Device
sysdefault:CARD=ICUSBAUDIO7D
    ICUSBAUDIO7D, USB Audio
    Default Audio Device
front:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    Front output / input
surround21:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    2.1 Surround output to Front and Subwoofer speakers
surround40:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    4.0 Surround output to Front and Rear speakers
surround41:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    4.1 Surround output to Front, Rear and Subwoofer speakers
surround50:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    5.0 Surround output to Front, Center and Rear speakers
surround51:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    5.1 Surround output to Front, Center, Rear and Subwoofer speakers
surround71:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    7.1 Surround output to Front, Center, Side, Rear and Woofer speakers
iec958:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    IEC958 (S/PDIF) Digital Audio Output
dmix:CARD=ICUSBAUDIO7D,DEV=0
    ICUSBAUDIO7D, USB Audio
    Direct sample mixing device
hw:CARD=sndrpihifiberry,DEV=0
    snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0
    Direct hardware device without any conversions
plughw:CARD=sndrpihifiberry,DEV=0
    snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0
    Hardware device with all software conversions
default:CARD=sndrpihifiberry
    snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0
    Default Audio Device
sysdefault:CARD=sndrpihifiberry
    snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0
    Default Audio Device
dmix:CARD=sndrpihifiberry,DEV=0
    snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0
    Direct sample mixing device
"""


def _fake_run_success(_args, **_kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stdout = APLAY_OUTPUT
    return result


def _fake_run_failure(_args, **_kwargs):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    return result


# ---------------------------------------------------------------------------
# list_alsa_devices
# ---------------------------------------------------------------------------


def test_list_alsa_devices_returns_all_device_names():
    with patch("subprocess.run", side_effect=_fake_run_success):
        devices = list_alsa_devices()

    names = [name for name, _ in devices]
    assert "null" in names
    assert "bluealsa" in names
    assert "jsm_dmix_sndrpihifiberry" in names
    assert "jsm_speaker_left" in names
    assert "hw:CARD=Loopback,DEV=0" in names
    assert "hw:CARD=Loopback,DEV=1" in names
    assert "hw:CARD=ICUSBAUDIO7D,DEV=0" in names
    assert "hw:CARD=sndrpihifiberry,DEV=0" in names
    assert "dmix:CARD=sndrpihifiberry,DEV=0" in names
    assert "iec958:CARD=ICUSBAUDIO7D,DEV=0" in names


def test_list_alsa_devices_description_is_first_indented_line():
    with patch("subprocess.run", side_effect=_fake_run_success):
        devices = list_alsa_devices()

    device_map = dict(devices)
    assert device_map["hw:CARD=sndrpihifiberry,DEV=0"] == (
        "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0"
    )
    assert device_map["hw:CARD=ICUSBAUDIO7D,DEV=0"] == "ICUSBAUDIO7D, USB Audio"
    assert device_map["hw:CARD=Loopback,DEV=0"] == "Loopback, Loopback PCM"
    assert device_map["null"] == (
        "Discard all samples (playback) or generate zero samples (capture)"
    )


def test_list_alsa_devices_device_without_description():
    """jsm_dmix_sndrpihifiberry has no description line."""
    with patch("subprocess.run", side_effect=_fake_run_success):
        devices = list_alsa_devices()

    device_map = dict(devices)
    assert device_map["jsm_dmix_sndrpihifiberry"] == ""


def test_list_alsa_devices_returns_empty_list_when_aplay_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert list_alsa_devices() == []


def test_list_alsa_devices_returns_empty_list_when_aplay_times_out():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aplay", 5)):
        assert list_alsa_devices() == []


def test_list_alsa_devices_returns_empty_list_on_nonzero_returncode():
    with patch("subprocess.run", side_effect=_fake_run_failure):
        assert list_alsa_devices() == []


# ---------------------------------------------------------------------------
# _parse_hw_format
# ---------------------------------------------------------------------------


def test_parse_hw_format_parses_hifiberry():
    assert (
        _parse_hw_format("hw:CARD=sndrpihifiberry,DEV=0") == "hw:sndrpihifiberry,0"
    )


def test_parse_hw_format_parses_loopback_dev0():
    assert _parse_hw_format("hw:CARD=Loopback,DEV=0") == "hw:Loopback,0"


def test_parse_hw_format_parses_loopback_dev1():
    assert _parse_hw_format("hw:CARD=Loopback,DEV=1") == "hw:Loopback,1"


def test_parse_hw_format_parses_usb_audio():
    assert _parse_hw_format("hw:CARD=ICUSBAUDIO7D,DEV=0") == "hw:ICUSBAUDIO7D,0"


def test_parse_hw_format_replaces_underscores_with_hyphens():
    assert (
        _parse_hw_format("hw:CARD=snd_rpi_hifiberry,DEV=0")
        == "hw:snd-rpi-hifiberry,0"
    )


def test_parse_hw_format_parses_plughw():
    # plughw: is a valid ALSA plugin prefix — parsed like hw:
    assert _parse_hw_format("plughw:CARD=Loopback,DEV=0") == "plughw:Loopback,0"


def test_parse_hw_format_parses_dmix():
    assert (
        _parse_hw_format("dmix:CARD=sndrpihifiberry,DEV=0")
        == "dmix:sndrpihifiberry,0"
    )


def test_parse_hw_format_returns_none_for_default_card():
    assert _parse_hw_format("default:CARD=Loopback") is None


def test_parse_hw_format_returns_none_for_sysdefault():
    assert _parse_hw_format("sysdefault:CARD=sndrpihifiberry") is None


def test_parse_hw_format_returns_none_for_simple_name():
    assert _parse_hw_format("jsm_speaker_left") is None
    assert _parse_hw_format("null") is None


def test_parse_hw_format_returns_none_for_plain_hw_numeric():
    assert _parse_hw_format("hw:0,0") is None


# ---------------------------------------------------------------------------
# _try_alsa_device
# ---------------------------------------------------------------------------


def test_try_alsa_device_returns_none_when_not_in_alsa_list():
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=[]),
    ):
        assert _try_alsa_device("hw:CARD=nonexistent,DEV=0") is None


def test_try_alsa_device_returns_portaudio_device_when_check_ok():
    """Simple ALSA name accepted by PortAudio → returns device with alsa_device_name."""
    info = {
        "name": "jsm_speaker_left",
        "max_output_channels": 128,
        "default_samplerate": 48000.0,
    }
    with (
        patch.object(sounddevice, "check_output_settings", return_value=None),
        patch.object(sounddevice, "query_devices", return_value=info),
    ):
        result = _try_alsa_device("jsm_speaker_left")

    assert result is not None
    assert result.alsa_device_name == "jsm_speaker_left"
    assert result.output_channels == 128
    assert result.sample_rate == 48000.0


def test_try_alsa_device_maps_hw_card_sndrpihifiberry_to_portaudio_device():
    """hw:CARD=sndrpihifiberry,DEV=0 should resolve to the PortAudio hifiberry device."""
    alsa_list = [
        (
            "hw:CARD=sndrpihifiberry,DEV=0",
            "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0",
        ),
    ]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
    ):
        result = _try_alsa_device("hw:CARD=sndrpihifiberry,DEV=0")

    assert result is not None
    assert result.index == 3  # snd_rpi_hifiberry_dacplus (hw:2,0)
    assert result.alsa_device_name is None  # mapped to a real PortAudio device


def test_try_alsa_device_maps_hw_card_loopback_dev0_to_portaudio_device():
    """hw:CARD=Loopback,DEV=0 should resolve to Loopback PCM (hw:0,0)."""
    alsa_list = [("hw:CARD=Loopback,DEV=0", "Loopback, Loopback PCM")]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
    ):
        result = _try_alsa_device("hw:CARD=Loopback,DEV=0")

    assert result is not None
    assert result.index == 0  # Loopback: PCM (hw:0,0)


def test_try_alsa_device_maps_hw_card_loopback_dev1_to_portaudio_device():
    """hw:CARD=Loopback,DEV=1 should resolve to Loopback PCM (hw:0,1)."""
    alsa_list = [("hw:CARD=Loopback,DEV=1", "Loopback, Loopback PCM")]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
    ):
        result = _try_alsa_device("hw:CARD=Loopback,DEV=1")

    assert result is not None
    assert result.index == 1  # Loopback: PCM (hw:0,1)


def test_try_alsa_device_maps_hw_card_icusbaudio_to_portaudio_device():
    """hw:CARD=ICUSBAUDIO7D,DEV=0 should resolve to the USB audio PortAudio device."""
    alsa_list = [("hw:CARD=ICUSBAUDIO7D,DEV=0", "ICUSBAUDIO7D, USB Audio")]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
    ):
        result = _try_alsa_device("hw:CARD=ICUSBAUDIO7D,DEV=0")

    assert result is not None
    assert result.index == 2  # ICUSBAUDIO7D: USB Audio (hw:1,0)


def test_try_alsa_device_returns_none_for_hw_card_format_when_portaudio_mapping_fails():
    """hw:CARD=...,DEV=... device that PortAudio can't find and can't be mapped via
    description should return None — not an AudioDevice that will fail at stream time."""
    # Device is in ALSA list but has no description → description-based mapping
    # cannot succeed → should return None rather than an unverifiable AudioDevice.
    alsa_list = [("hw:CARD=UnknownCard,DEV=0", "")]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=[]),
    ):
        result = _try_alsa_device("hw:CARD=UnknownCard,DEV=0")

    assert result is None


def test_try_alsa_device_falls_back_to_alsa_device_when_no_portaudio_match():
    """ALSA-only device (no matching PortAudio entry) gets an ALSA-named AudioDevice."""
    alsa_list = [("jsm_dmix_sndrpihifiberry", "")]
    with (
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=alsa_list),
        patch.object(_mod, "query_devices", return_value=[]),
    ):
        result = _try_alsa_device("jsm_dmix_sndrpihifiberry")

    assert result is not None
    assert result.alsa_device_name == "jsm_dmix_sndrpihifiberry"
    assert result.output_channels == 2
    assert result.sample_rate == 48000.0


def test_try_alsa_device_uses_safe_defaults_when_portaudio_query_fails():
    with (
        patch.object(sounddevice, "check_output_settings", return_value=None),
        patch.object(
            sounddevice,
            "query_devices",
            side_effect=sounddevice.PortAudioError("err", -1, ""),
        ),
    ):
        result = _try_alsa_device("jsm_speaker_left")

    assert result is not None
    assert result.output_channels == 2
    assert result.sample_rate == 48000.0


# ---------------------------------------------------------------------------
# resolve_audio_device
# ---------------------------------------------------------------------------


def test_resolve_audio_device_resolves_default_device():
    with patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES):
        result = resolve_audio_device(None)

    assert result.is_default is True
    assert result.index == 15
    assert result.name == "default"


def test_resolve_audio_device_resolves_device_by_index():
    with patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES):
        result = resolve_audio_device("2")

    assert result.index == 2
    assert "ICUSBAUDIO7D" in result.name


def test_resolve_audio_device_resolves_device_by_name_prefix():
    with patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES):
        result = resolve_audio_device("snd_rpi_hifiberry")

    assert result.index == 3


def test_resolve_audio_device_resolves_jsm_speaker_left_by_name_prefix():
    with patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES):
        result = resolve_audio_device("jsm_speaker_left")

    assert result.index == 13


def test_resolve_audio_device_resolves_hw_card_format_on_linux():
    """hw:CARD=sndrpihifiberry,DEV=0 should map to PortAudio index 3 on Linux."""
    with (
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
        patch("sys.platform", "linux"),
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=ALSA_DEVICES),
    ):
        result = resolve_audio_device("hw:CARD=sndrpihifiberry,DEV=0")

    assert result.index == 3


def test_resolve_audio_device_resolves_alsa_only_device_on_linux():
    """Pure ALSA device (null, bluealsa) not in PortAudio list → ALSA-named AudioDevice."""
    with (
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
        patch("sys.platform", "linux"),
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=ALSA_DEVICES),
    ):
        result = resolve_audio_device("bluealsa")

    assert result is not None
    assert result.alsa_device_name == "bluealsa"


def test_resolve_audio_device_raises_for_unknown_device():
    with (
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
        patch("sys.platform", "linux"),
        patch.object(
            sounddevice,
            "check_output_settings",
            side_effect=ValueError("not found"),
        ),
        patch.object(_mod, "list_alsa_devices", return_value=ALSA_DEVICES),
    ):
        with pytest.raises(ValueError, match="nonexistent_device"):
            resolve_audio_device("nonexistent_device")


# ---------------------------------------------------------------------------
# list_audio_devices (CLI output)
# ---------------------------------------------------------------------------


def _run_list_audio_devices_cli(*, platform: str = "linux") -> str:
    out = StringIO()
    with (
        patch.object(_mod, "query_devices", return_value=PORTAUDIO_DEVICES),
        patch.object(_mod, "list_alsa_devices", return_value=ALSA_DEVICES),
        patch("sys.platform", platform),
        patch("sys.stdout", out),
    ):
        _cli.list_audio_devices()
    return out.getvalue()


def test_list_audio_devices_cli_header_present():
    output = _run_list_audio_devices_cli()
    assert "Available audio output devices:" in output


def test_list_audio_devices_cli_all_portaudio_devices_listed():
    output = _run_list_audio_devices_cli()
    assert "[0] Loopback: PCM (hw:0,0)" in output
    assert "[2] ICUSBAUDIO7D: USB Audio (hw:1,0)" in output
    assert (
        "[3] snd_rpi_hifiberry_dacplus: HiFiBerry DAC+ HiFi pcm512x-hifi-0 (hw:2,0)"
        in output
    )
    assert "[12] jsm_dmix_sndrpihifiberry" in output
    assert "[16] dmix" in output


def test_list_audio_devices_cli_default_device_marked():
    output = _run_list_audio_devices_cli()
    assert "[15] default (default)" in output


def test_list_audio_devices_cli_channels_and_sample_rate_shown():
    output = _run_list_audio_devices_cli()
    # ICUSBAUDIO7D has 8 channels at 44100 Hz
    assert "Channels: 8, Sample rate: 44100.0 Hz" in output
    # hifiberry has 2 channels at 44100 Hz
    assert "Channels: 2, Sample rate: 44100.0 Hz" in output


def test_list_audio_devices_cli_alsa_section_shown_on_linux():
    output = _run_list_audio_devices_cli(platform="linux")
    assert "ALSA devices (use by name with --audio-device):" in output
    assert "hw:CARD=sndrpihifiberry,DEV=0" in output
    assert "snd_rpi_hifiberry_dacplus, HiFiBerry DAC+ HiFi pcm512x-hifi-0" in output
    assert "hw:CARD=ICUSBAUDIO7D,DEV=0" in output
    assert "iec958:CARD=ICUSBAUDIO7D,DEV=0" in output
    assert "null" in output
    assert "bluealsa" in output


def test_list_audio_devices_cli_alsa_section_omitted_on_non_linux():
    output = _run_list_audio_devices_cli(platform="darwin")
    assert "ALSA devices" not in output


def test_list_audio_devices_cli_device_without_description_shown_without_description_line():
    """jsm_dmix_sndrpihifiberry has no description — only the name line is printed."""
    output = _run_list_audio_devices_cli()
    lines = output.splitlines()
    jsm_idx = next(
        i
        for i, l in enumerate(lines)
        if "jsm_dmix_sndrpihifiberry" in l and l.startswith("  jsm")
    )
    # The next line should be the next device entry (2-space prefix), not a blank
    # line or a description indent (7-space prefix).
    next_line = lines[jsm_idx + 1] if jsm_idx + 1 < len(lines) else ""
    assert next_line.startswith("  ") and not next_line.startswith("       ")


def test_list_audio_devices_cli_select_hint_shown():
    output = _run_list_audio_devices_cli()
    assert "sendspin --audio-device" in output
