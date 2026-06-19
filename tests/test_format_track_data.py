"""
Tests for tidal_api.utils.format_track_data.

Covers:
- Regression: original fields are still present and correct
- New metadata fields: artists, track_number, disc_number, explicit,
  popularity, audio_quality, audio_modes, isrc, version, release_date
- Relational / artwork fields: cover_url, album_id, artist_id, artist_ids
- Provenance fields: date_added, copyright
- Audio analysis fields (bpm, key, key_scale, peak, replay_gain) are
  only included when TIDAL provides non-zero/non-None values
- source_track_id passthrough
- Graceful handling of missing optional attributes
"""
import sys
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tidal_api.utils import format_track_data


def _make_album(**kwargs):
    """Build a mock Album whose .image(size) returns a resources.tidal.com URL."""
    cover = kwargs.pop('cover', 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
    image_url = kwargs.pop(
        'image_url',
        'https://resources.tidal.com/images/aaaaaaaa/bbbb/cccc/dddd/eeeeeeeeeeee/640x640.jpg',
    )
    return SimpleNamespace(
        name=kwargs.pop('name', 'Test Album'),
        id=kwargs.pop('id', 200),
        cover=cover,
        image=lambda size, _u=image_url: _u,
    )


def _make_track(**kwargs):
    """Build a minimal mock Track object with sensible defaults."""
    artist = SimpleNamespace(
        name=kwargs.pop('artist_name', 'Test Artist'),
        id=kwargs.pop('artist_id', 100),
    )
    album = kwargs.pop('album', None) or _make_album(name=kwargs.pop('album_name', 'Test Album'))

    defaults = dict(
        id=123,
        name='Test Track',
        artist=artist,
        artists=[artist],
        album=album,
        duration=200,
        track_num=1,
        volume_num=1,
        explicit=False,
        popularity=50,
        audio_quality='LOSSLESS',
        audio_modes=['STEREO'],
        isrc='USABC1234567',
        copyright=None,
        version=None,
        tidal_release_date=None,
        # Date the user saved the track (favourites/collection context only)
        user_date_added=None,
        # Audio analysis — default to "not set"
        bpm=0,
        key=None,
        key_scale=None,
        peak=0.0,
        replay_gain=0.0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Regression: original fields
# ---------------------------------------------------------------------------

class TestOriginalFields:
    def test_id(self):
        track = _make_track(id=999)
        assert format_track_data(track)['id'] == 999

    def test_title(self):
        track = _make_track(name='Bleed')
        assert format_track_data(track)['title'] == 'Bleed'

    def test_artist(self):
        track = _make_track(artist_name='Meshuggah')
        assert format_track_data(track)['artist'] == 'Meshuggah'

    def test_album(self):
        track = _make_track(album_name='obZen')
        assert format_track_data(track)['album'] == 'obZen'

    def test_duration(self):
        track = _make_track(duration=443)
        assert format_track_data(track)['duration'] == 443

    def test_url_format(self):
        track = _make_track(id=396319304)
        assert format_track_data(track)['url'] == 'https://tidal.com/browse/track/396319304?u'

    def test_artist_missing_name_attribute(self):
        track = _make_track()
        track.artist = object()  # no .name
        assert format_track_data(track)['artist'] == 'Unknown'

    def test_album_missing_name_attribute(self):
        track = _make_track()
        track.album = object()  # no .name
        assert format_track_data(track)['album'] == 'Unknown'

    def test_source_track_id_included_when_provided(self):
        track = _make_track()
        result = format_track_data(track, source_track_id='111')
        assert result['source_track_id'] == '111'

    def test_source_track_id_absent_when_not_provided(self):
        track = _make_track()
        assert 'source_track_id' not in format_track_data(track)


# ---------------------------------------------------------------------------
# New metadata fields
# ---------------------------------------------------------------------------

class TestNewMetadataFields:
    def test_artists_list(self):
        a1 = SimpleNamespace(name='Artist A')
        a2 = SimpleNamespace(name='Artist B')
        track = _make_track(artists=[a1, a2])
        assert format_track_data(track)['artists'] == ['Artist A', 'Artist B']

    def test_artists_empty_when_none(self):
        track = _make_track()
        track.artists = None
        assert format_track_data(track)['artists'] == []

    def test_track_number(self):
        track = _make_track(track_num=3)
        assert format_track_data(track)['track_number'] == 3

    def test_disc_number(self):
        track = _make_track(volume_num=2)
        assert format_track_data(track)['disc_number'] == 2

    def test_explicit_false(self):
        track = _make_track(explicit=False)
        assert format_track_data(track)['explicit'] is False

    def test_explicit_true(self):
        track = _make_track(explicit=True)
        assert format_track_data(track)['explicit'] is True

    def test_popularity(self):
        track = _make_track(popularity=72)
        assert format_track_data(track)['popularity'] == 72

    def test_audio_quality(self):
        track = _make_track(audio_quality='HI_RES_LOSSLESS')
        assert format_track_data(track)['audio_quality'] == 'HI_RES_LOSSLESS'

    def test_audio_modes(self):
        track = _make_track(audio_modes=['DOLBY_ATMOS'])
        assert format_track_data(track)['audio_modes'] == ['DOLBY_ATMOS']

    def test_isrc(self):
        track = _make_track(isrc='DE1AH2308803')
        assert format_track_data(track)['isrc'] == 'DE1AH2308803'

    def test_version_present(self):
        track = _make_track(version='15th Anniversary Remastered 2023 Edition')
        assert format_track_data(track)['version'] == '15th Anniversary Remastered 2023 Edition'

    def test_version_none(self):
        track = _make_track(version=None)
        assert format_track_data(track)['version'] is None

    def test_release_date_isoformat(self):
        dt = datetime(2024, 11, 1, tzinfo=timezone.utc)
        track = _make_track(tidal_release_date=dt)
        assert format_track_data(track)['release_date'] == dt.isoformat()

    def test_release_date_none(self):
        track = _make_track(tidal_release_date=None)
        assert format_track_data(track)['release_date'] is None


# ---------------------------------------------------------------------------
# Relational / artwork fields
# ---------------------------------------------------------------------------

class TestRelationalAndArtworkFields:
    def test_cover_url_from_album_image(self):
        album = _make_album(image_url='https://resources.tidal.com/images/x/640x640.jpg')
        track = _make_track(album=album)
        assert format_track_data(track)['cover_url'] == 'https://resources.tidal.com/images/x/640x640.jpg'

    def test_cover_url_none_when_album_has_no_cover(self):
        album = _make_album(cover=None)
        track = _make_track(album=album)
        assert format_track_data(track)['cover_url'] is None

    def test_cover_url_none_when_image_raises(self):
        # tidalapi raises if the cover UUID is unusable — must be swallowed, not propagated.
        def _boom(size):
            raise ValueError('bad cover')
        album = SimpleNamespace(name='Album', id=200, cover='uuid', image=_boom)
        track = _make_track(album=album)
        assert format_track_data(track)['cover_url'] is None

    def test_album_id_stringified(self):
        album = _make_album(id=49464968)
        track = _make_track(album=album)
        assert format_track_data(track)['album_id'] == '49464968'

    def test_album_id_none_when_missing(self):
        track = _make_track()
        track.album = SimpleNamespace(name='Album')  # no id
        assert format_track_data(track)['album_id'] is None

    def test_artist_id_stringified(self):
        track = _make_track(artist_id=3996865)
        assert format_track_data(track)['artist_id'] == '3996865'

    def test_artist_id_none_when_missing(self):
        track = _make_track()
        track.artist = SimpleNamespace(name='Artist')  # no id
        assert format_track_data(track)['artist_id'] is None

    def test_artist_ids_list_stringified(self):
        a1 = SimpleNamespace(name='Artist A', id=1)
        a2 = SimpleNamespace(name='Artist B', id=2)
        track = _make_track(artists=[a1, a2])
        assert format_track_data(track)['artist_ids'] == ['1', '2']

    def test_artist_ids_skip_entries_without_id(self):
        a1 = SimpleNamespace(name='Artist A', id=1)
        a2 = SimpleNamespace(name='Artist B')  # no id
        track = _make_track(artists=[a1, a2])
        assert format_track_data(track)['artist_ids'] == ['1']

    def test_artist_ids_empty_when_none(self):
        track = _make_track()
        track.artists = None
        assert format_track_data(track)['artist_ids'] == []


# ---------------------------------------------------------------------------
# Provenance fields: date_added, copyright
# ---------------------------------------------------------------------------

class TestProvenanceFields:
    def test_date_added_from_user_date_added(self):
        dt = datetime(2023, 5, 2, tzinfo=timezone.utc)
        track = _make_track(user_date_added=dt)
        assert format_track_data(track)['date_added'] == dt.isoformat()

    def test_date_added_falls_back_to_date_added(self):
        dt = datetime(2022, 1, 9, tzinfo=timezone.utc)
        track = _make_track(user_date_added=None, date_added=dt)
        assert format_track_data(track)['date_added'] == dt.isoformat()

    def test_date_added_none_when_absent(self):
        track = _make_track(user_date_added=None)
        assert format_track_data(track)['date_added'] is None

    def test_copyright_present(self):
        track = _make_track(copyright='℗ 2023 Test Records')
        assert format_track_data(track)['copyright'] == '℗ 2023 Test Records'

    def test_copyright_none(self):
        track = _make_track(copyright=None)
        assert format_track_data(track)['copyright'] is None


# ---------------------------------------------------------------------------
# Audio analysis fields — conditional on TIDAL having data
# ---------------------------------------------------------------------------

class TestAudioAnalysisFields:
    def test_bpm_included_when_set(self):
        track = _make_track(bpm=120)
        assert format_track_data(track)['bpm'] == 120

    def test_bpm_excluded_when_zero(self):
        track = _make_track(bpm=0)
        assert 'bpm' not in format_track_data(track)

    def test_key_included_when_set(self):
        track = _make_track(key='C')
        assert format_track_data(track)['key'] == 'C'

    def test_key_excluded_when_none(self):
        track = _make_track(key=None)
        assert 'key' not in format_track_data(track)

    def test_key_scale_included_when_set(self):
        track = _make_track(key_scale='MINOR')
        assert format_track_data(track)['key_scale'] == 'MINOR'

    def test_key_scale_excluded_when_none(self):
        track = _make_track(key_scale=None)
        assert 'key_scale' not in format_track_data(track)

    def test_peak_included_when_set(self):
        track = _make_track(peak=0.966051)
        assert abs(format_track_data(track)['peak'] - 0.966051) < 1e-6

    def test_peak_excluded_when_zero(self):
        track = _make_track(peak=0.0)
        assert 'peak' not in format_track_data(track)

    def test_replay_gain_included_when_set(self):
        track = _make_track(replay_gain=-10.46)
        assert abs(format_track_data(track)['replay_gain'] - (-10.46)) < 1e-6

    def test_replay_gain_excluded_when_zero(self):
        track = _make_track(replay_gain=0.0)
        assert 'replay_gain' not in format_track_data(track)

    def test_all_audio_analysis_present(self):
        track = _make_track(bpm=140, key='F#', key_scale='MAJOR', peak=0.9, replay_gain=-8.0)
        result = format_track_data(track)
        assert result['bpm'] == 140
        assert result['key'] == 'F#'
        assert result['key_scale'] == 'MAJOR'
        assert result['peak'] == 0.9
        assert result['replay_gain'] == -8.0


# ---------------------------------------------------------------------------
# Missing optional attributes (defensive getattr)
# ---------------------------------------------------------------------------

class TestMissingAttributes:
    def test_handles_track_without_optional_fields(self):
        """A bare-minimum track object should not raise."""
        artist = SimpleNamespace(name='Artist')
        album = SimpleNamespace(name='Album')
        track = SimpleNamespace(id=1, name='Track', artist=artist, album=album, duration=180)
        result = format_track_data(track)
        assert result['id'] == 1
        assert result['title'] == 'Track'
        # Optional fields default gracefully
        assert result['artists'] == []
        assert result['artist_id'] is None
        assert result['artist_ids'] == []
        assert result['album_id'] is None
        assert result['cover_url'] is None
        assert result['copyright'] is None
        assert result['date_added'] is None
        assert result['explicit'] is False
        assert result['release_date'] is None
        assert 'bpm' not in result
        assert 'key' not in result
