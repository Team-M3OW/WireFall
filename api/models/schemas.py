from pydantic import BaseModel


class RequestData(BaseModel):
    method: str
    path: str
    protocol: str
    request_body: str


class PassRequestBody(BaseModel):
    mongo_id: str


class RuleBody(BaseModel):
    rule: str
