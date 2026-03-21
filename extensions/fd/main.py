import os
import subprocess

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction

ICON_FILE = "images/icon.svg"


class FdExtension(Extension):

    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())


def _find_fd():
    try:
        subprocess.run(["fd", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _get_search_dirs(extension):
    raw = extension.preferences.get("search_dirs", "")
    if raw and raw.strip():
        dirs = [d.strip() for d in raw.strip().splitlines() if d.strip()]
        return [d for d in dirs if os.path.isdir(d)]
    return [os.path.expanduser("~")]


def _run_fd(query_terms, search_dirs, max_results):
    args = ["fd", "--full-path", "--max-results", str(max_results)]

    search_type = None
    filtered_terms = []

    for term in query_terms:
        if term in ("-f", "-file"):
            search_type = "f"
        elif term in ("-d", "-dir"):
            search_type = "d"
        elif term:
            filtered_terms.append(term)

    if search_type:
        args.extend(["--type", search_type])

    if filtered_terms:
        args.append(filtered_terms[0])
        for term in filtered_terms[1:]:
            args.extend(["--and", term])

    args.extend(search_dirs)

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        output = result.stdout.strip()
        if output:
            return output.split("\n")
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return []


def _make_items(paths):
    items = []
    for path in paths:
        normalized = path.rstrip("/")
        is_dir = os.path.isdir(normalized)
        filename = os.path.basename(normalized)

        if is_dir:
            name = filename + "/"
            description = path
        else:
            name = filename
            description = path

        items.append(ExtensionResultItem(
            icon=ICON_FILE,
            name=name,
            description=description,
            on_enter=OpenAction(path),
            on_alt_enter=CopyToClipboardAction(path),
        ))

    items.sort(key=lambda x: (not os.path.isdir(x.name.rstrip("/")), len(x.description), x.name.lower()))
    return items


class KeywordQueryEventListener(EventListener):

    def on_event(self, event, extension):
        argument = event.get_argument() or ""
        terms = argument.strip().split()

        if not terms:
            return RenderResultListAction([ExtensionResultItem(
                icon=ICON_FILE,
                name="Search files with fd",
                description="Type a search term after 'fd'",
                on_enter=DoNothingAction(),
            )])

        max_results = int(extension.preferences.get("max_results", "20"))
        search_dirs = _get_search_dirs(extension)

        paths = _run_fd(terms, search_dirs, max_results)

        if not paths:
            return RenderResultListAction([ExtensionResultItem(
                icon=ICON_FILE,
                name="No results found",
                description="Try a different search term",
                on_enter=DoNothingAction(),
            )])

        items = _make_items(paths)
        return RenderResultListAction(items)


class ItemEnterEventListener(EventListener):

    def on_event(self, event, extension):
        data = event.get_data()
        if data and isinstance(data, dict) and data.get("action") == "copy":
            return CopyToClipboardAction(data.get("path", ""))
        return None


if __name__ == "__main__":
    FdExtension().run()
