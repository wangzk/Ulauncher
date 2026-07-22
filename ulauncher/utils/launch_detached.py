from __future__ import annotations

import logging
import os
import subprocess
import sys

from gi.repository import GLib

from ulauncher.utils.systemd_controller import SystemdController

logger = logging.getLogger()


def detach_child() -> None:
    """
    A utility function which runs in the child process launched by spawn_async
    and before execing the supplied command.
    """
    # Use setsid to take "session leader" status so that the child pid is
    # definitely detached from the parent ulauncher process
    os.setsid()

    # Don't redirect the standard file descriptors unless connected to a terminal.
    if not sys.stdout.isatty():
        return

    # Reopen the stdin, stdout, and stderr file descriptors to /dev/null. This
    # ensures the stdout/stderr are no longer connected to the terminal. This
    # serves a similar purpose as the standard "nohup" command. Any processes
    # connected to the terminal will get the interrupt signal when "Ctrl-C" is
    # called, so this redirection prevents the child process from exiting when
    # ulauncher is interrupted. Unlike "nohup", stdout and stderr are not sent
    # to a file but sent to /dev/null instead.
    with open("/dev/null", "w+b") as null_fp:
        null_fd = null_fp.fileno()
        for fp in [sys.stdin, sys.stdout, sys.stderr]:
            orig_fd = fp.fileno()
            fp.close()
            os.dup2(null_fd, orig_fd)


def _get_x11_display_name() -> str | None:
    """
    Return the X11 display Ulauncher is connected to.

    Prefers the live GDK display name over the static $DISPLAY env var, which may be
    missing or stale when Ulauncher is started via D-Bus activation or as a systemd
    user service (the manager environment is imported asynchronously at login).
    """
    try:
        from gi.repository import GdkX11

        if x11_display := GdkX11.X11Display.get_default():
            return x11_display.get_name()
    except (ImportError, RuntimeError):
        pass
    return os.environ.get("DISPLAY")


def launch_detached(cmd: list[str], working_dir: str | None = None) -> None:
    use_systemd_run = SystemdController("ulauncher").is_active()

    env = dict(os.environ.items())
    # Make sure GDK apps aren't forced to use x11 on wayland due to ulauncher's need to run
    # under X11 for proper centering.
    if env.get("GDK_BACKEND") != "wayland":
        env.pop("GDK_BACKEND", None)

    # Propagate the X11 display Ulauncher is actually connected to, so launched
    # programs target the same display instead of auto-detecting the Xorg session.
    # $DISPLAY may be absent when Ulauncher is D-Bus/systemd activated.
    if display_name := _get_x11_display_name():
        env["DISPLAY"] = display_name

    # Sync QT_FONT_DPI with the current Xft.dpi so Qt apps match the screen DPI.
    # xrdb is X11-only and may not be available (e.g. under Wayland), so silently
    # ignore failures. Falls back to 96 (the standard X11 default) when Xft.dpi
    # is not found or xrdb is unavailable.
    try:
        result = subprocess.run(
            ["xrdb", "-query"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Xft.dpi:"):
                dpi = line.split(":", 1)[1].strip()
                if dpi:
                    env["QT_FONT_DPI"] = dpi
                    break
        else:
            env["QT_FONT_DPI"] = "96"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        env["QT_FONT_DPI"] = "96"

    # When launched via systemd-run, explicitly forward display-related env vars
    # through --setenv so they reach the program even if the systemd user manager
    # environment has drifted from Ulauncher's own environment.
    if use_systemd_run:
        setenv_args: list[str] = []
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY"):
            if value := env.get(key):
                setenv_args.extend(["--setenv", f"{key}={value}"])
        cmd = ["systemd-run", "--user", "--scope", *setenv_args, *cmd]

    try:
        envp = [f"{k}={v}" for k, v in env.items()]
        GLib.spawn_async(
            argv=cmd,
            envp=envp,
            flags=GLib.SpawnFlags.SEARCH_PATH_FROM_ENVP | GLib.SpawnFlags.SEARCH_PATH,
            child_setup=None if use_systemd_run else detach_child,
            # the python gi wrapper has a bug, not actually allowing to pass working_directory as None
            **({"working_directory": working_dir} if working_dir else {}),
        )
    except (TypeError, GLib.Error):
        logger.exception('Could not launch "%s"', cmd)


def open_detached(path_or_url: str) -> None:
    launch_detached(["xdg-open", path_or_url])
