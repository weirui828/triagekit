import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .hashing import sha256_obj
from .schemas import ContractValidateResponse, LabelContract


def load_contract_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_text()
    return json.loads(raw) if p.suffix == ".json" else yaml.safe_load(raw)


def contract_hash(c: LabelContract) -> str:
    return sha256_obj(c.model_dump(mode="json"))


def validate_contract(data: Any) -> ContractValidateResponse:
    try:
        c = LabelContract.model_validate(data)
    except ValidationError as e:
        return ContractValidateResponse(ok=False, errors=[_fmt(err) for err in e.errors()])
    errors: list[str] = []
    if c.positive.definition.strip() == "" or c.negative.definition.strip() == "":
        errors.append("positive and negative definitions must be nonempty")
    if c.categories.required and not c.categories.allowed:
        errors.append("categories.required=true but categories.allowed is empty")
    if len(set(c.categories.allowed)) != len(c.categories.allowed):
        errors.append("categories.allowed contains duplicates")
    if errors:
        return ContractValidateResponse(ok=False, errors=errors)
    return ContractValidateResponse(ok=True, errors=[], contract=c, contract_hash=contract_hash(c))


def _fmt(err: dict[str, Any]) -> str:
    loc = ".".join(str(x) for x in err.get("loc", ()))
    return f"{loc}: {err['msg']}" if loc else err["msg"]
