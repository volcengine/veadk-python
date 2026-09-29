from pathlib import Path
import tomllib

from packaging.requirements import Requirement


def test_studio_requires_agentkit_sdk_with_tos_credential_type() -> None:
    project = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = next(
        Requirement(value)
        for value in metadata["project"]["dependencies"]
        if Requirement(value).name == "agentkit-sdk-python"
    )

    assert requirement.specifier.contains("0.8.5")
    assert not requirement.specifier.contains("0.8.4")
