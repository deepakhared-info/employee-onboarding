from pydantic import BaseModel, ConfigDict

from src.provisioning.models import ProvisioningService, ProvisioningStatus


class ProvisioningTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service: ProvisioningService
    status: ProvisioningStatus
    attempts: int
    last_error: str | None
