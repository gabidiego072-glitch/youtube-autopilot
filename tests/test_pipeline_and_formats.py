import pytest

from app.core.errors import InvalidStateTransitionError
from app.models import VideoProject
from app.models.enums import ProjectStatus, VideoFormat
from app.services.production.formats import get_format_spec, validate_target_duration
from app.services.production.pipeline import ALLOWED_TRANSITIONS, can_transition, transition
from tests.conftest import make_settings


def test_every_status_has_transition_rules():
    assert set(ALLOWED_TRANSITIONS) == set(ProjectStatus)


def test_transition_rules():
    assert can_transition(ProjectStatus.DRAFT, ProjectStatus.SCRIPT_READY)
    assert not can_transition(ProjectStatus.DRAFT, ProjectStatus.PUBLISHED)
    project = VideoProject(status=ProjectStatus.DRAFT)
    with pytest.raises(InvalidStateTransitionError):
        transition(project, ProjectStatus.READY_TO_PUBLISH)
    transition(project, ProjectStatus.SCRIPT_READY)
    assert project.status == ProjectStatus.SCRIPT_READY


def test_format_specs():
    settings = make_settings()
    short = get_format_spec(VideoFormat.SHORT, settings)
    long = get_format_spec(VideoFormat.LONG, settings)
    assert (short.width, short.height, short.aspect_ratio) == (1080, 1920, "9:16")
    assert (long.width, long.height, long.aspect_ratio) == (1920, 1080, "16:9")
    assert short.max_duration_seconds == 180
    validate_target_duration(short, 60)
    with pytest.raises(ValueError):
        validate_target_duration(short, 181)
    with pytest.raises(ValueError):
        validate_target_duration(long, 120)
