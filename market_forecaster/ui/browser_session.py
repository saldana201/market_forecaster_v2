"""Small Streamlit v2 component that stores only an opaque browser session handle."""
from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping

import streamlit as st


BROWSER_STORAGE_ACTION_KEY = "_browser_session_storage_action"
BROWSER_STORAGE_COMPONENT_KEY = "_browser_session_storage_bridge"
BROWSER_STORAGE_KEY = "market_forecaster_browser_session"


_JS = """
export default function({ data, setStateValue }) {
    const storageKey = data?.storage_key || "market_forecaster_browser_session";
    const action = data?.action || "read";
    const value = data?.value || "";

    try {
        if (action === "set" && value) {
            window.localStorage.setItem(storageKey, value);
        } else if (action === "clear") {
            window.localStorage.removeItem(storageKey);
        }
    } catch (_) {
        // Storage can be unavailable in hardened/private browser contexts.
    }

    let handle = "";
    try {
        handle = window.localStorage.getItem(storageKey) || "";
    } catch (_) {
        handle = "";
    }

    setStateValue("snapshot", { ready: true, handle });
}
"""


_bridge_component = st.components.v2.component(
    "market_forecaster.browser_session_bridge",
    html='<span id="mf-browser-session-bridge" style="display:none"></span>',
    js=_JS,
)


@dataclass(frozen=True)
class BrowserStorageSnapshot:
    ready: bool
    handle: str


def queue_browser_session_set(state: MutableMapping, handle: str) -> None:
    state[BROWSER_STORAGE_ACTION_KEY] = {"action": "set", "value": str(handle or "")}


def queue_browser_session_clear(state: MutableMapping) -> None:
    state[BROWSER_STORAGE_ACTION_KEY] = {"action": "clear", "value": ""}


def render_browser_session_bridge(state: MutableMapping) -> BrowserStorageSnapshot:
    action_row = state.pop(BROWSER_STORAGE_ACTION_KEY, None)
    action = "read"
    value = ""
    if isinstance(action_row, dict):
        action = str(action_row.get("action") or "read")
        value = str(action_row.get("value") or "")

    result = _bridge_component(
        data={
            "storage_key": BROWSER_STORAGE_KEY,
            "action": action,
            "value": value,
        },
        default={"snapshot": {"ready": False, "handle": ""}},
        on_snapshot_change=lambda: None,
        key=BROWSER_STORAGE_COMPONENT_KEY,
    )

    snapshot = result.snapshot if isinstance(result.snapshot, dict) else {}
    ready = bool(snapshot.get("ready"))
    handle = str(snapshot.get("handle") or "")

    # The Python side already knows the intended value for a write/clear action.
    # Use it immediately instead of waiting for the frontend callback rerun.
    if action == "set" and value:
        return BrowserStorageSnapshot(ready=True, handle=value)
    if action == "clear":
        return BrowserStorageSnapshot(ready=True, handle="")

    return BrowserStorageSnapshot(ready=ready, handle=handle)


def browser_user_agent() -> str:
    try:
        return str(st.context.headers.get("User-Agent") or "")
    except Exception:
        return ""
