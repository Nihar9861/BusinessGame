"""A fake Telegram server so handlers can be tested end-to-end without a token or internet."""
import json
import time

from telegram.request import BaseRequest


class FakeRequest(BaseRequest):
    def __init__(self):
        super().__init__()
        self.calls = []          # (method, params)
        self.next_id = 1000

    @property
    def read_timeout(self):
        return 5

    async def initialize(self): ...
    async def shutdown(self): ...

    async def do_request(self, url, method, request_data=None, read_timeout=None, write_timeout=None,
                         connect_timeout=None, pool_timeout=None):
        name = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((name, params))
        if name == "getMe":
            res = {"id": 1, "is_bot": True, "first_name": "BoardKing", "username": "BoardKingBot"}
        elif name in ("sendMessage", "sendPhoto", "editMessageMedia", "editMessageText", "editMessageCaption"):
            self.next_id += 1
            res = {"message_id": params.get("message_id", self.next_id), "date": int(time.time()),
                   "chat": {"id": int(params["chat_id"]), "type": "private"}}
        else:
            res = True
        return 200, json.dumps({"ok": True, "result": res}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]
