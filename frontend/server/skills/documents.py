"""Edit only SKILL.md while preserving every other archive member."""

import io
import zipfile
from pathlib import PurePosixPath

from .archive import validate_skill_archive
from .repository import SkillRepositoryError


def replace_skill_document(content: bytes, document: str) -> bytes:
    original = validate_skill_archive(content)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        names = [
            name
            for name in source.namelist()
            if PurePosixPath(name).parts[0] != "__MACOSX"
        ]
        path = next(
            (name for name in names if PurePosixPath(name).as_posix() == "SKILL.md"),
            None,
        )
        if path is None:
            path = next(
                name
                for name in names
                if len(PurePosixPath(name).parts) == 2
                and PurePosixPath(name).name == "SKILL.md"
            )
        with zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                target.writestr(
                    info,
                    document.encode("utf-8")
                    if info.filename == path
                    else source.read(info),
                )
    result = output.getvalue()
    updated = validate_skill_archive(result)
    if updated.name != original.name:
        raise SkillRepositoryError(
            "SKILL_VERSION_NAME_MISMATCH", "新版本必须保留原技能名称", status_code=422
        )
    return result
