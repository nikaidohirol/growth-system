"""Pydantic 请求/响应模型"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """统一响应信封：code=0 成功"""
    code: int = 0
    message: str = "success"
    data: Any = None


class LoginReq(BaseModel):
    uid: str
    password: str


class UserOut(BaseModel):
    id: str
    uid: str
    name: str
    role: Literal["Student", "Counsellor", "Dean"]
    sex: str | None = None
    politicsStatus: str | None = None
    phone: str | None = None
    email: str | None = None
    classId: str | None = None
    periods: str | None = None
    college: str | None = None
    major: str | None = None
    photo: str | None = None
    title: str | None = None
    counsellorName: str | None = None

    class Config:
        from_attributes = True


class StudentCreate(BaseModel):
    uid: str
    name: str
    password: str = "123456"
    sex: str | None = None
    nation: str | None = None
    politicsStatus: str | None = None
    birthday: str | None = None
    phone: str | None = None
    email: str | None = None
    classId: str | None = None
    periods: str | None = None
    college: str | None = None
    major: str | None = None
    origin: str | None = None
    address: str | None = None


class StudentUpdate(BaseModel):
    name: str | None = None
    sex: str | None = None
    nation: str | None = None
    politicsStatus: str | None = None
    birthday: str | None = None
    phone: str | None = None
    email: str | None = None
    classId: str | None = None
    periods: str | None = None
    college: str | None = None
    major: str | None = None
    origin: str | None = None
    address: str | None = None


class AuditSubmitReq(BaseModel):
    status: Literal["通过", "驳回"]
    opinion: str = ""


class GpaCompIn(BaseModel):
    sid: str
    semester: str
    college: str
    major: str
    mutual: float
    comp: float
    gpa: float
    gpaRank: int
    compRank: int
    maxRank: int


class ExperienceIn(BaseModel):
    startDate: str
    endDate: str
    college: str
    major: str
    classId: str | None = None
    eyewitness: str | None = None


class PasswordChange(BaseModel):
    oldPassword: str
    newPassword: str = Field(min_length=6, max_length=32)


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    sessionId: str | None = None
    images: list[str] = Field(default=[], max_length=4,
                              description="随消息发送的图片 URL（/files/xxx），多模态视觉理解")


class FormAssistReq(BaseModel):
    entityKey: str
    description: str = Field(min_length=2, max_length=2000)


class AuditAssistReq(BaseModel):
    entityKey: str
    item: dict
