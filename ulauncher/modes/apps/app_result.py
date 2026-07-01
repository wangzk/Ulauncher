from __future__ import annotations

import contextlib
import logging
import operator
from os.path import basename

from ulauncher import paths
from ulauncher.internals.result import Result
from ulauncher.utils.desktopappinfo import DesktopAppInfo
from ulauncher.utils.json_utils import json_load, json_save

logger = logging.getLogger()
app_starts_path = f"{paths.STATE}/app_starts.json"
app_starts: dict[str, int] = json_load(app_starts_path)


class AppResult(Result):
    searchable = True
    app_id = ""
    _executable = ""
    _name_en = ""
    actions = {"launch": {"name": "Launch application", "icon": "system-run"}}

    def __init__(self, app_info: DesktopAppInfo) -> None:
        super().__init__(
            name=app_info.get_display_name(),
            icon=app_info.get_string("Icon") or "",
            description=app_info.get_description() or app_info.get_generic_name() or "",
            keywords=app_info.get_keywords(),
            app_id=app_info.get_id(),
            # TryExec is what we actually want (name of/path to exec), but it's often not specified
            # get_executable uses Exec, which is always specified, but it will return the actual executable.
            # Sometimes the actual executable is not the app to start, but a wrappers like "env" or "sh -c"
            _executable=basename(app_info.get_string("TryExec") or app_info.get_executable() or ""),
            # Untranslated Name field (usually English) as fallback for cross-language search.
            # e.g. "Nutstore" when display name is "坚果云", or "Baidu Netdisk" for "百度网盘"
            _name_en=app_info.get_string("Name") or "",
        )

    @staticmethod
    def from_id(app_id: str) -> AppResult | None:
        # Suppress errors due to app being uninstalled/not found
        with contextlib.suppress(TypeError):
            if app_info := DesktopAppInfo.new(app_id):
                return AppResult(app_info)
        return None

    @staticmethod
    def get_top_app_ids() -> list[str]:
        sorted_tuples = sorted(app_starts.items(), key=operator.itemgetter(1), reverse=True)
        return [*map(operator.itemgetter(0), sorted_tuples)]

    def get_searchable_fields(self) -> list[tuple[str, float]]:
        frequency_weight = 1.0
        sorted_app_ids = AppResult.get_top_app_ids()
        if count := len(sorted_app_ids):
            index = sorted_app_ids.index(self.app_id) if self.app_id in sorted_app_ids else count
            frequency_weight = 1.0 - (index / count * 0.1) + 0.05

        fields: list[tuple[str, float]] = [
            (self.name, 1 * frequency_weight),
            (self._executable, 0.8 * frequency_weight),  # command names, such as "baobab" or "nautilus"
            (self.description, 0.7 * frequency_weight),
            *[(k, 0.6 * frequency_weight) for k in self.keywords],
        ]
        # Add untranslated name (usually English) as fallback for cross-language search.
        # This ensures apps can be found by their original name even when the display name
        # is localized (e.g., Flatpak apps with Chinese names like "坚果云"/"百度网盘").
        if self._name_en and self._name_en != self.name:
            fields.append((self._name_en, 0.9 * frequency_weight))
        return fields

    def bump_starts(self) -> None:
        starts = app_starts.get(self.app_id, 0)
        app_starts[self.app_id] = starts + 1
        json_save(app_starts, app_starts_path)
