from __future__ import annotations

from googleapiclient.discovery import HttpRequest

from datetime import datetime
from typing import Any, Dict, List, Literal, Protocol, Type, TypedDict, TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Connection
    from types import TracebackType


class OAuthCreds(TypedDict):
    access_token: str
    expires_in: int
    refresh_token: str
    scope: str
    token_type: str


class ConnectionContextManager(Protocol):
    async def __aenter__(self) -> Connection:
        ...

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...


class PostgresPool(Protocol):
    async def execute(self, query: str, *args: Any, timeout: float | None = None) -> str:
        ...

    async def fetch(self, query: str, *args: Any, timeout: float | None = None) -> List[Any]:
        ...

    async def fetchrow(self, query: str, *args: Any, timeout: float | None = None) -> Any | None:
        ...

    async def fetchval(self, query: str, *args: Any, timeout: float | None = None) -> Any | None:
        ...

    async def close(self) -> None:
        ...

    def acquire(self, *, timeout: float | None = None) -> ConnectionContextManager:
        ...

    def release(self, connection: Connection) -> None:
        ...


class Resource(Protocol):
    def courses(self) -> Resource:
        ...

    def announcements(self) -> Resource:
        ...

    def courseWorkMaterials(self) -> Resource:
        ...

    def courseWork(self) -> Resource:
        ...

    def studentSubmissions(self) -> Resource:
        ...

    def list(self, **kwargs: str | int) -> HttpRequest:
        ...


class LavalinkNodeParams(TypedDict):
    host: str
    port: int
    password: str
    region: str
    https: bool


class Secrets(TypedDict):
    token: str
    testing_token: str
    helper_token: str
    rickroll_token: str
    other_rickroll_token: str
    github_token: str
    postgres_dns: str
    redis_password: str
    vps_ip: str
    topgg_auth: str
    lavalink: LavalinkNodeParams


class Announcement(TypedDict):
    updateTime: str
    alternateLink: str
    courseId: str
    text: str
    scheduledTime: str
    creationTime: str
    assigneeMode: str
    creatorUserId: str
    state: str
    materials: List[Attachment]
    individualStudentOptions: Dict[Literal["studentIds"], List[str]]
    id: str


class Attachment(TypedDict):
    youtubeVideo: Dict[str, str] | None
    driveFile: Dict[Literal["driveFile", "shareMode"], Dict[str, str] | str] | None
    link: Dict[str, str] | None
    form: Dict[str, str] | None


class Course(TypedDict):
    updateTime: str
    room: str
    name: str
    alternateLink: str
    enrollmentCode: str
    section: str
    guardiansEnabled: bool
    courseGroupEmail: str
    creationTime: str
    teacherGroupEmail: str
    courseMaterialSets: List[Dict[Literal["materials", "title"], List[Attachment] | str]]
    calendarId: str
    teacherFolder: Dict[str, str]
    ownerId: str
    courseState: str
    id: str
    descriptionHeading: str
    description: str


class CourseWork(TypedDict):
    updateTime: str
    courseId: str
    assigneeMode: str
    id: str
    submissionModificationMode: str
    creatorUserId: str
    dueDate: Dict[str, int]
    state: str
    dueTime: Dict[str, int]
    topicId: str
    description: str
    assignment: Dict[str, Dict[str, str]]
    scheduledTime: str
    associatedWithDeveloper: bool
    maxPoints: float
    workType: str
    alternateLink: str
    title: str
    creationTime: str
    materials: List[Attachment]
    individualStudentsOptions: Dict[Literal["studentIds"], List[str]]
    multipleChoiceQuestion: Dict[Literal["choices"], List[str]]
    studentSubmissions: Any | None


class CourseWorkMaterials(TypedDict):
    topicId: str
    updateTime: str
    description: str
    alternateLink: str
    courseId: str
    scheduledTime: str
    creationTime: str
    assigneeMode: str
    creatorUserId: str
    state: str
    materials: List[Attachment]
    title: str
    individualStudentOptions: Dict[Literal["studentIds"], List[str]]
    id: str


class GradeHistory(TypedDict):
    gradeTimestamp: str
    actorUserId: str
    pointsEarned: float
    maxPoints: float
    gradeChangeType: str


class StudentSubmissions(TypedDict):
    draftGrade: float
    shortAnswerSubmission: Dict[Literal["answer"], str]
    updateTime: str
    alternateLink: str
    courseId: str
    userId: str
    creationTime: str
    submissionHistory: List[Dict[Literal["stateHistory", "gradeHistory"], Dict[str, str] | GradeHistory]]
    associatedWithDeveloper: bool
    late: bool
    state: str
    courseWorkId: str
    courseWorkType: str
    multipleChoiceSubmission: Dict[Literal["answer"], str]
    assignedGrade: float
    assignmentSubmission: Dict[Literal["attachments"], List[Attachment]]
    id: str


class WebhookData(TypedDict):
    user_id: int
    course_id: int
    guild_id: int
    channel_id: int
    course_name: str
    url: str
    last_date: datetime
    last_announcement_post: datetime
    last_material_post: datetime
    last_assignment_post: datetime


Post = Announcement | CourseWork | CourseWorkMaterials
