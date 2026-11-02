"""Project lifecycle state machine shared by Shorts and long-form production."""

from app.core.errors import InvalidStateTransitionError
from app.models.enums import ProjectStatus as S
from app.models.video_project import VideoProject

ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.DRAFT: {S.SCRIPT_READY, S.ARCHIVED},
    S.SCRIPT_READY: {S.SCRIPT_READY, S.RENDERING, S.METADATA_READY, S.ARCHIVED},
    S.RENDERING: {S.RENDERED, S.FAILED},
    S.RENDERED: {S.METADATA_READY, S.RENDERING, S.SCRIPT_READY, S.ARCHIVED},
    S.METADATA_READY: {S.METADATA_READY, S.RENDERING, S.READY_TO_PUBLISH, S.SCRIPT_READY, S.ARCHIVED},
    S.READY_TO_PUBLISH: {S.PUBLISHED, S.METADATA_READY, S.FAILED, S.ARCHIVED},
    S.PUBLISHED: {S.ARCHIVED},
    S.FAILED: {S.DRAFT, S.SCRIPT_READY, S.ARCHIVED},
    S.ARCHIVED: set(),
}


def can_transition(current: S, target: S) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(project: VideoProject, target: S) -> None:
    if not can_transition(project.status, target):
        raise InvalidStateTransitionError(f"Cannot move project from '{project.status.value}' to '{target.value}'.")
    project.status = target
