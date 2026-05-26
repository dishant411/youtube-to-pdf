from __future__ import annotations

import json
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import urlopen

from app.models import TranscriptSegment, VideoReference

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEO_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
DEFAULT_TRANSCRIPT_LANGUAGES = ("en", "hi")


class VideoValidationError(ValueError):
    """Raised when the URL does not match the accepted YouTube formats."""


class TranscriptUnavailableError(RuntimeError):
    """Raised when a transcript cannot be retrieved."""


def _contains_embedded_url(values: Iterable[str]) -> bool:
    for value in values:
        lowered = value.lower()
        if "http://" in lowered or "https://" in lowered:
            return True
    return False


def _is_valid_video_id(video_id: str) -> bool:
    return len(video_id) == 11 and all(char in VIDEO_ID_CHARS for char in video_id)


def _canonical_url(video_id: str) -> str:
    return "https://www.youtube.com/watch?v={video_id}".format(video_id=video_id)


def parse_video_reference(raw_input: str) -> VideoReference:
    value = raw_input.strip()
    if not value:
        raise VideoValidationError("Empty input is not a valid YouTube URL.")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise VideoValidationError("Only http and https URLs are accepted.")
    if parsed.fragment:
        raise VideoValidationError("URL fragments are not supported.")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise VideoValidationError("Only youtube.com and youtu.be URLs are accepted.")

    query_values = [item for values in parse_qs(parsed.query, keep_blank_values=True).values() for item in values]
    if _contains_embedded_url(query_values):
        raise VideoValidationError("Embedded URLs inside query parameters are not allowed.")

    video_id = None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.hostname == "youtu.be":
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 1:
            raise VideoValidationError("Short links must point directly to a video.")
        video_id = path_parts[0]
    elif parsed.path == "/watch":
        video_id = query.get("v", [None])[0]
    elif parsed.path.startswith("/shorts/"):
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 2 or path_parts[0] != "shorts":
            raise VideoValidationError("Shorts URLs must be in /shorts/<video-id> format.")
        video_id = path_parts[1]
    elif parsed.path.startswith("/embed/"):
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 2 or path_parts[0] != "embed":
            raise VideoValidationError("Embed URLs must be in /embed/<video-id> format.")
        video_id = path_parts[1]
    else:
        raise VideoValidationError("Unsupported YouTube URL format.")

    if not video_id or not _is_valid_video_id(video_id):
        raise VideoValidationError("Malformed or missing YouTube video ID.")

    return VideoReference(raw_input=value, video_id=video_id, canonical_url=_canonical_url(video_id))


def dedupe_references(references: Sequence[VideoReference]) -> List[VideoReference]:
    unique = []
    seen = set()
    for reference in references:
        if reference.video_id in seen:
            continue
        unique.append(reference)
        seen.add(reference.video_id)
    return unique


def fetch_video_title(canonical_url: str, timeout: int = 10) -> Optional[str]:
    params = urlencode({"url": canonical_url, "format": "json"}, quote_via=quote)
    endpoint = "https://www.youtube.com/oembed?{params}".format(params=params)
    try:
        with urlopen(endpoint, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    title = payload.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def _import_transcript_api():
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi


def _convert_entries(raw_entries: Iterable[dict]) -> List[TranscriptSegment]:
    segments = []
    for item in raw_entries:
        if isinstance(item, dict):
            text = item.get("text", "")
            start = float(item.get("start", 0.0))
            duration = float(item.get("duration", 0.0))
        else:
            text = getattr(item, "text", "")
            start = float(getattr(item, "start", 0.0))
            duration = float(getattr(item, "duration", 0.0))
        segments.append(TranscriptSegment(text=text, start=start, duration=duration))
    return segments


def _fetch_with_class_api(
    api_class,
    video_id: str,
    preferred_languages: Sequence[str],
) -> Tuple[List[TranscriptSegment], Optional[str]]:
    last_error: Optional[Exception] = None
    for language_code in preferred_languages:
        try:
            entries = api_class.get_transcript(video_id, languages=[language_code])
            return _convert_entries(entries), language_code
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise TranscriptUnavailableError("No transcript languages were configured.")


def _find_preferred_transcript(transcript_list, preferred_languages: Sequence[str]):
    for language_code in preferred_languages:
        if hasattr(transcript_list, "find_transcript"):
            try:
                return transcript_list.find_transcript([language_code])
            except Exception:
                pass
        if hasattr(transcript_list, "find_generated_transcript"):
            try:
                return transcript_list.find_generated_transcript([language_code])
            except Exception:
                pass
        if hasattr(transcript_list, "find_manually_created_transcript"):
            try:
                return transcript_list.find_manually_created_transcript([language_code])
            except Exception:
                pass
    return next(iter(transcript_list))


def _fetch_with_instance_api(
    api_class,
    video_id: str,
    preferred_languages: Sequence[str],
) -> Tuple[List[TranscriptSegment], Optional[str]]:
    api = api_class()
    if hasattr(api, "fetch"):
        fetched = api.fetch(video_id, languages=list(preferred_languages))
        language = getattr(fetched, "language_code", None)
        if hasattr(fetched, "to_raw_data"):
            return _convert_entries(fetched.to_raw_data()), language
        return _convert_entries(list(fetched)), language
    if hasattr(api, "list") or hasattr(api, "list_transcripts"):
        transcript_list = api.list(video_id) if hasattr(api, "list") else api.list_transcripts(video_id)
        transcript = _find_preferred_transcript(transcript_list, preferred_languages)
        language = getattr(transcript, "language_code", None)
        fetched = transcript.fetch()
        if hasattr(fetched, "to_raw_data"):
            return _convert_entries(fetched.to_raw_data()), language
        return _convert_entries(list(fetched)), language
    raise TranscriptUnavailableError("Unsupported youtube-transcript-api interface.")


def fetch_transcript_data(
    video_id: str,
    preferred_languages: Sequence[str] = DEFAULT_TRANSCRIPT_LANGUAGES,
) -> Tuple[List[TranscriptSegment], Optional[str]]:
    api_class = _import_transcript_api()
    try:
        if hasattr(api_class, "get_transcript"):
            return _fetch_with_class_api(api_class, video_id, preferred_languages)
        return _fetch_with_instance_api(api_class, video_id, preferred_languages)
    except Exception as exc:
        raise TranscriptUnavailableError(str(exc)) from exc
