from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"


class AssignmentStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class RubricSource(StrEnum):
    TEACHER_PROVIDED = "TEACHER_PROVIDED"
    AI_GENERATED = "AI_GENERATED"
    AI_GENERATED_TEACHER_EDITED = "AI_GENERATED_TEACHER_EDITED"


class RubricStatus(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


class SubmissionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    COLLECTING = "COLLECTING"
    PARSED = "PARSED"
    READY_FOR_GRADING = "READY_FOR_GRADING"
    GRADING = "GRADING"
    GRADED = "GRADED"
    FAILED = "FAILED"


class SubmissionFileParseStatus(StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    PARSE_PARTIAL = "PARSE_PARTIAL"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class GradingRunStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    NEEDS_TEACHER_REVIEW = "NEEDS_TEACHER_REVIEW"
    APPROVED = "APPROVED"
    OVERRIDDEN = "OVERRIDDEN"


class VivaDifficulty(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
