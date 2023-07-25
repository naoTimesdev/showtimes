"""
This file is part of Showtimes Backend Project.
Copyright 2022-present naoTimes Project <https://github.com/naoTimesdev/showtimes>.

Showtimes is free software: you can redistribute it and/or modify it under the terms of the
Affero GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

Showtimes is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the Affero GNU General Public License for more details.

You should have received a copy of the Affero GNU General Public License along with Showtimes.
If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, TypeAlias

from showtimes.tooling import get_logger
from showtimes.utils import make_uuid

__all__ = (
    "PubSubHandler",
    "get_pubsub",
)
PSCallback: TypeAlias = Callable[[Any], None]
PSAsyncCallback: TypeAlias = Callable[[Any], Awaitable[None]]
PSDualCallback: TypeAlias = PSAsyncCallback | PSCallback
logger = get_logger("Showtimes.Controllers.PubSub")


class _BreakApart:
    def __str__(self):
        return "..."

    def __repr__(self) -> str:
        return "..."

    def __bool__(self):
        return False


BREAKER = _BreakApart()


class MessageHandler:
    def __init__(self, identifier: str, subscribe: str, *, handler: PubSubHandler):
        self._id = identifier
        self._subscriber = subscribe
        self._msg_queue = asyncio.Queue[Any]()

        self._closing_state = False
        self._handler = handler

    @property
    def identifier(self) -> str:
        return self._id

    async def close(self, *, skip_handler: bool = False):
        self._closing_state = True
        logger.debug(f"Closing {self._subscriber} at {self.identifier}")
        await self._msg_queue.put(BREAKER)

        if not skip_handler:
            await self._handler.unsubscribe(self._subscriber, self._id)

    async def publish(self, message: Any):
        if self._closing_state:
            return  # ignore
        logger.debug(f"New payload received for {self._subscriber} at {self.identifier}")
        await self._msg_queue.put(message)

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        try:
            while True:
                try:
                    data = await asyncio.wait_for(self._msg_queue.get(), timeout=10.0)
                    if data is BREAKER:
                        break
                    yield data
                except asyncio.TimeoutError:
                    if self._closing_state:
                        break
                    continue
        except asyncio.CancelledError:
            pass

        await self.close()


class PubSubHandler:
    def __init__(self, *, loop: asyncio.AbstractEventLoop | None = None):
        logger.debug("Initializing PubSubHandler")
        self._loop = loop or asyncio.get_event_loop()

        self._message_handler: dict[str, list[MessageHandler]] = {}
        self._lock_unsub = asyncio.Lock()

        self._running_tasks: dict[str, asyncio.Task] = {}

    async def unsubscribe(self, topic: str, identifier: str):
        async with self._lock_unsub:
            topic_handler = self._message_handler.get(topic)
            if topic_handler is None:
                return
            idx_del = None
            for idx, handler in enumerate(topic_handler):
                if handler.identifier == identifier:
                    idx_del = idx
                    break
            if idx_del is not None:
                logger.debug(f"Removing {identifier} from {topic}")
                self._message_handler[topic].pop(idx_del)

    def subscribe(self, topic: str) -> MessageHandler:
        if topic not in self._message_handler:
            self._message_handler[topic] = []

        identifier = make_uuid()
        logger.debug(f"New subscriber {identifier} for {topic}")
        handler = MessageHandler(str(identifier), topic, handler=self)
        self._message_handler[topic].append(handler)
        return handler

    async def close(self):
        for topic in self._message_handler.keys():
            for handler in self._message_handler[topic]:
                await handler.close(skip_handler=True)
            self._message_handler[topic].clear()

        running_pub = list(self._running_tasks.values())
        logger.debug(f"Closing {len(running_pub)} running tasks")
        for task in running_pub:
            if not task.done():
                task.cancel()

    def _task_cb_pub(self, task: asyncio.Task):
        task_name = task.get_name()
        logger.debug(f"Task {task_name} done, deregistering")
        try:
            del self._running_tasks[task_name]
        except KeyError:
            pass

    def publish(self, topic: str, payload: Any):
        topic_handler = self._message_handler.get(topic)
        if topic_handler is None:
            return
        ts = int(datetime.utcnow().timestamp())
        for handler in topic_handler:
            payload_name = f"shpubsubv2:{topic}:{handler.identifier}:{ts}"
            logger.debug(f"Publishing {payload_name}")
            task = asyncio.create_task(handler.publish(payload), name=payload_name)
            task.add_done_callback(self._task_cb_pub)
            self._running_tasks[payload_name] = task


_PUBSUB = PubSubHandler()


def get_pubsub() -> PubSubHandler:
    return _PUBSUB
