"""Output specifications for YouTube Shorts and long-form videos."""

from dataclasses import dataclass

from app.core.config import Settings
from app.models.enums import VideoFormat


@dataclass(frozen=True)
class FormatSpec:
    format: VideoFormat
    width: int
    height: int
    fps: int
    min_duration_seconds: int
    max_duration_seconds: int | None
    video_bitrate: str
    audio_bitrate: str

    @property
    def aspect_ratio(self) -> str:
        return "9:16" if self.height > self.width else "16:9"


def get_format_spec(video_format: VideoFormat, settings: Settings) -> FormatSpec:
    if video_format == VideoFormat.SHORT:
        return FormatSpec(
            format=VideoFormat.SHORT,
            width=1080,
            height=1920,
            fps=30,
            min_duration_seconds=5,
            max_duration_seconds=settings.shorts_max_duration_seconds,
            video_bitrate="8M",
            audio_bitrate="192k",
        )
    return FormatSpec(
        format=VideoFormat.LONG,
        width=1920,
        height=1080,
        fps=30,
        min_duration_seconds=settings.long_form_min_duration_seconds,
        max_duration_seconds=None,
        video_bitrate="12M",
        audio_bitrate="192k",
    )


def validate_target_duration(spec: FormatSpec, seconds: int) -> None:
    if seconds < spec.min_duration_seconds:
        raise ValueError(f"{spec.format.value} videos must be at least {spec.min_duration_seconds}s (got {seconds}s).")
    if spec.max_duration_seconds is not None and seconds > spec.max_duration_seconds:
        raise ValueError(f"{spec.format.value} videos must be at most {spec.max_duration_seconds}s (got {seconds}s).")


DEFAULT_TARGET_DURATION = {VideoFormat.SHORT: 45, VideoFormat.LONG: 480}
