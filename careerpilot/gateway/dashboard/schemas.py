from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationsListResponse(BaseModel):
    success: bool = True
    conversations: list[ConversationOut]
    count: int


class ConversationTurnOut(BaseModel):
    role: str
    content: str
    created_at: str


class ConversationDetailResponse(BaseModel):
    success: bool = True
    conversation: ConversationOut
    turns: list[ConversationTurnOut]


class ConversationRenameRequest(BaseModel):
    title: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ChatResponse(BaseModel):
    success: bool = True
    conversation: ConversationOut
    message: ChatMessage


class ApplicationOut(BaseModel):
    id: int
    company: str
    role: str
    date_applied: str
    source: str | None = None
    status: str
    notes: str | None = None


class ApplicationsResponse(BaseModel):
    success: bool = True
    applications: list[ApplicationOut]
    count: int


class NoteOut(BaseModel):
    id: str
    company: str
    text: str
    score: float | None = None


class NotesResponse(BaseModel):
    success: bool = True
    notes: list[NoteOut]
    count: int


class ProfileResponse(BaseModel):
    success: bool = True
    content: str


class ProfileUpdateRequest(BaseModel):
    content: str


class SettingsOut(BaseModel):
    provider: str
    model: str
    has_api_key: bool
    base_url: str | None = None
    embedding_provider: str
    embedding_model: str
    has_embedding_api_key: bool
    job_search_platforms: list[str] = Field(default_factory=list)
    job_search_default_location: str | None = None
    experimental_tools_enabled: bool


class SettingsResponse(BaseModel):
    success: bool = True
    settings: SettingsOut


class SettingsUpdateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    job_search_platforms: list[str] | None = None
    job_search_default_location: str | None = None
    experimental_tools_enabled: bool | None = None


class SimpleMessageResponse(BaseModel):
    success: bool = True
    message: str


class SkillOut(BaseModel):
    name: str
    description: str
    path: str


class SkillsResponse(BaseModel):
    success: bool = True
    skills: list[SkillOut]
    count: int


class SkillCreateRequest(BaseModel):
    name: str
    trigger_keywords: list[str] = Field(default_factory=list)
    instructions: str


class SkillCreateResponse(BaseModel):
    success: bool = True
    skill: SkillOut


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


# ------------------------------------------------------
# Dashboard
# ------------------------------------------------------


class DashboardStats(BaseModel):
    conversations: int
    applications: int
    skills: int
    memories: int


class DashboardRecentApplication(BaseModel):
    company: str
    role: str
    status: str
    date_applied: str


class DashboardRecentSkill(BaseModel):
    name: str
    description: str


class DashboardResponse(BaseModel):
    success: bool = True

    stats: DashboardStats

    recent_applications: list[DashboardRecentApplication]

    recent_skills: list[DashboardRecentSkill]

    provider: str

    model: str
