"""Pure dataset checker entry points."""

from vision_doctor.checkers.annotation import (
    AnnotationCheckConfig,
    check_annotations,
)

__all__ = ["AnnotationCheckConfig", "check_annotations"]
