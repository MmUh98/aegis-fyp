from pydantic import BaseModel


class RegistrationResponse(BaseModel):
    success: bool
    filename: str
    falcon_key_hash: str
    manifest_hash: str
    phash: str
    tx_hash: str
    block_number: int
    explorer_url: str
    message: str
