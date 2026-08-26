from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ieb_protocol.qualification_monitor_models import QualificationGroup, QualificationItem


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(value: str) -> str:
    cleaned = INVALID_FILENAME.sub("_", str(value or "")).rstrip(" .")
    return cleaned or "未命名"


class NativeExportStore:
    def __init__(self, output_directory: Path, run_id: str) -> None:
        self.run_root = Path(output_directory).resolve() / safe_filename(run_id)
        self.files_root = self.run_root / "files"
        self.run_root.mkdir(parents=True, exist_ok=False)
        self._entries: dict[str, tuple[str, Path]] = {}

    def save(
        self,
        group: QualificationGroup,
        item: QualificationItem,
        index: int,
        content: bytes,
    ) -> Path:
        group_name = safe_filename(group.name)
        filename = f"{index:02d}-{safe_filename(item.name)}_{safe_filename(item.code)}.xlsx"
        directory = self.files_root / group_name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        self._entries[item.code] = (group_name, path)
        return path

    def build_archive(self) -> Path:
        archive = self.run_root / "资质监控-全部原生导出.zip"
        temporary = archive.with_suffix(".tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for group_name, path in self._entries.values():
                output.write(path, arcname=f"{group_name}/{path.name}")
        temporary.replace(archive)
        return archive
