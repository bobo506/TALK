"""受管bridge首次启动/HTTP回退不回放旧私信；普通SDK保持原语义。"""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock,patch
import httpx
from TALK.client import TalkClient


class ManagedMessageCursorTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self,**kwargs):
        c=TalkClient('http://127.0.0.1:1','fixture-key',**kwargs);c._member={'id':'agent:fixture'}
        return c
    async def test_failed_initial_tail_never_falls_back_to_history_zero(self):
        c=self.make_client(start_from_latest=True);received=[];c.on_message(lambda m:received.append(m))
        c.fetch_history=AsyncMock(side_effect=[httpx.ConnectError('fixture outage'),[{'id':42}],[{'id':43,'from':'human:fixture'}]])
        with self.assertRaises(httpx.ConnectError):await c._poll_once()
        self.assertFalse(c._message_cursor_initialized);self.assertEqual(received,[])
        await c._poll_once()
        self.assertEqual([r['id'] for r in received],[43])
        self.assertEqual(c.fetch_history.call_args_list[-1].kwargs,{'since':42,'limit':100})
    async def test_empty_initial_history_does_not_reinitialize_and_skip_new_dm(self):
        c=self.make_client(start_from_latest=True);received=[];c.on_message(lambda m:received.append(m))
        c.fetch_history=AsyncMock(side_effect=[[],[{'id':1,'from':'human:fixture'}],[]])
        await c._poll_once();await c._poll_once()
        self.assertEqual([r['id'] for r in received],[1])
        self.assertEqual(sum(call.kwargs=={'limit':1} for call in c.fetch_history.call_args_list),1)
    async def test_new_dm_in_ws_connect_gap_and_buffered_duplicate_are_delivered_once(self):
        c=self.make_client(start_from_latest=True);received=[];c.on_message(lambda m:received.append(m))
        c.fetch_history=AsyncMock(side_effect=[[{'id':9}],[{'id':10,'from':'human:fixture'}]])
        await c._initialize_message_cursor()
        class WS:
            async def __aenter__(self):return self
            async def __aexit__(self,*_):return False
            def __aiter__(self):return self.iterate()
            async def iterate(self):yield json.dumps({'type':'message','payload':{'id':10,'from':'human:fixture'}})
        with patch('TALK.client.talk_client.websockets.connect',return_value=WS()):
            with self.assertRaises(ConnectionError):await c._run_websocket_session()
        self.assertEqual([r['id'] for r in received],[10])
    async def test_default_sdk_keeps_explicit_history_replay(self):
        c=self.make_client();received=[];c.on_message(lambda m:received.append(m))
        c.fetch_history=AsyncMock(return_value=[{'id':5,'from':'human:fixture'}])
        await c._poll_once()
        self.assertEqual([r['id'] for r in received],[5])
        c.fetch_history.assert_awaited_once_with(since=0,limit=100)


if __name__=='__main__':unittest.main()
