from pydantic import BaseModel, Field


class SensorData(BaseModel):
    time_sec: int = 0
    distance: int = 0
    agtron: float = 0.0
    roc: float = 0.0
    t1: float = 0.0
    ror1: float = 0.0
    t2: float = 0.0
    ror2: float = 0.0
    t1_valid: int = 0
    t2_valid: int = 0
    boom1_count: int = 0
    boom2_count: int = 0


class DeviceInfo(BaseModel):
    name: str
    address: str
    rssi: int


class StatusResponse(BaseModel):
    connected: bool
    device_name: str | None = None
    device_address: str | None = None
    packet_count: int = 0
    scanning: bool = False


class ConnectRequest(BaseModel):
    address: str


class IntervalRequest(BaseModel):
    interval: float = Field(gt=0, le=60)


class FieldsRequest(BaseModel):
    fields: list[str]


FIELD_META = {
    "time_sec":        ("检测时间", "s"),
    "distance":        ("TOF 距离", "mm"),
    "agtron":          ("色值", "Agt"),
    "roc":             ("色值变化率", "Agt/min"),
    "t1":              ("探针 TC1", "℃"),
    "ror1":            ("TC1 升温速率", "℃/min"),
    "t2":              ("探针 TC2", "℃"),
    "ror2":            ("TC2 升温速率", "℃/min"),
    "t1_valid":        ("TC1 有效性", ""),
    "t2_valid":        ("TC2 有效性", ""),
    "boom1_count":     ("一爆次数", ""),
    "boom2_count":     ("二爆次数", ""),
}
