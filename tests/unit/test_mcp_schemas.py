"""Strict schema and exported-output contract tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from telematics.mcp.export_schemas import write_output_schemas
from telematics.mcp.schemas import INPUT_MODELS, TOOL_INPUT_MODELS, TOOL_OUTPUT_MODELS


@pytest.mark.unit
def test_all_tool_input_models_forbid_unknown_fields() -> None:
    assert len(TOOL_INPUT_MODELS) == 11
    assert all(model.model_config["extra"] == "forbid" for model in INPUT_MODELS)
    for model in INPUT_MODELS:
        with pytest.raises(ValidationError):
            model.model_validate({"unknown_field": True})


@pytest.mark.unit
def test_each_tool_output_schema_has_schema_version_and_exports(tmp_path) -> None:
    assert len(TOOL_OUTPUT_MODELS) == 11
    paths = write_output_schemas(tmp_path)

    assert len(paths) == 11
    for tool_name, model in TOOL_OUTPUT_MODELS.items():
        document = json.loads((tmp_path / f"{tool_name}.json").read_text(encoding="utf-8"))
        assert "schema_version" in document["properties"]
        assert document == model.model_json_schema()


@pytest.mark.unit
def test_checked_in_schemas_match_the_output_models() -> None:
    root = Path(__file__).resolve().parents[2]

    for tool_name, model in TOOL_OUTPUT_MODELS.items():
        document = json.loads(
            (root / "docs" / "schemas" / f"{tool_name}.json").read_text(encoding="utf-8")
        )
        assert document == model.model_json_schema(), tool_name
