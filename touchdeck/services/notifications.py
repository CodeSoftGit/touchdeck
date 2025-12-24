from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable

from dbus_next.aio import MessageBus
from dbus_next.constants import MessageType
from dbus_next.message import Message


@dataclass(slots=True)
class SystemNotification:
    app_name: str
    summary: str
    body: str
    expire_ms: int | None = None


class NotificationListener:
    """Watches freedesktop.org system notifications and forwards them to the UI."""

    def __init__(
        self,
        on_notify: Callable[[SystemNotification], None]
        | Callable[[SystemNotification], Awaitable[None]],
    ) -> None:
        self._on_notify = on_notify
        self._bus: MessageBus | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            bus = await MessageBus().connect()
            await self._become_monitor(bus)
            bus.add_message_handler(self._on_message)
            self._bus = bus
        except Exception:
            # If monitoring is unavailable, fail silently so the UI stays alive.
            self._started = False
            self._bus = None

    @staticmethod
    async def _become_monitor(bus: MessageBus) -> None:
        reply = await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus.Monitoring",
                member="BecomeMonitor",
                signature="asu",
                body=[["interface='org.freedesktop.Notifications'"], 0],
            )
        )
        if reply is None:
            raise RuntimeError("No reply from D-Bus")
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(str(reply.body))

    def _on_message(self, msg: Message) -> bool:
        if msg.message_type != MessageType.METHOD_CALL:
            return False
        if msg.interface != "org.freedesktop.Notifications" or msg.member != "Notify":
            return False
        body = msg.body or []
        if len(body) < 5:
            return False

        app_name = str(body[0] or "").strip()
        summary = str(body[3] or "").strip()
        text = str(body[4] or "").strip()
        expire_ms: int | None = None
        if len(body) > 7:
            try:
                expire_val = int(body[7])
                if expire_val > 0:
                    expire_ms = expire_val
            except Exception:
                expire_ms = None

        if not summary and not text:
            return False

        notification = SystemNotification(
            app_name=app_name, summary=summary, body=text, expire_ms=expire_ms
        )
        self._dispatch(notification)
        return False

    def _dispatch(self, notification: SystemNotification) -> None:
        if not self._on_notify:
            return
        try:
            if inspect.iscoroutinefunction(self._on_notify):
                asyncio.create_task(self._on_notify(notification))
            else:
                self._on_notify(notification)
        except Exception:
            # Keep notification errors from crashing the UI.
            pass
