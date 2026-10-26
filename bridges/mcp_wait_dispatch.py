"""A bounded wait lane for MCP. Normal tools retain their serialized ordering."""
import threading
from bridges.mcp_wait_context import CURRENT_WAIT, WaitContext, WaitCancelled


class WaitLane:
    def __init__(self, dispatch, respond, error):
        self.dispatch,self.respond,self.error=dispatch,respond,error
        self.lock=threading.RLock()
        self.current=None

    @staticmethod
    def handles(name, arguments):
        return name=='talk_wait_tasks' or (name=='talk_follow_tasks' and arguments.get('action','next') in ('start','next'))

    def submit(self, request_id, name, arguments):
        with self.lock:
            if self.current is not None:
                self.respond(request_id,{'content':[{'type':'text','text':'wait_in_progress: another wait is active on this connection'}],'isError':True})
                return
            context=WaitContext()
            thread=threading.Thread(target=self.run,args=(request_id,name,arguments,context),daemon=True)
            self.current=(request_id,context,thread)
            thread.start()

    def run(self, request_id, name, arguments, context):
        token=CURRENT_WAIT.set(context)
        response=None
        try:
            value=self.dispatch(name,arguments)
            response={'content':[{'type':'text','text':__import__('json').dumps(value,ensure_ascii=False)}],'isError':False}
        except WaitCancelled:
            response={'content':[{'type':'text','text':'request_cancelled: read wait stopped; executor tasks were not canceled'}],
                      'isError':True,'_meta':{'error_code':'request_cancelled'}}
        except Exception as exc:
            from bridges.talk_task_tools import TalkToolError
            if isinstance(exc,(KeyError,TypeError,ValueError,TalkToolError)):
                response={'content':[{'type':'text','text':f'{name} 失败：{exc}'}],'isError':True}
            else:
                self.error(request_id,-32603,'wait_execution_failed')
        finally:
            CURRENT_WAIT.reset(token)
            with self.lock:
                if self.current is not None and self.current[1] is context:self.current=None
        if response is not None:self.respond(request_id,response)

    def cancel(self, request_id):
        with self.lock:
            if self.current is not None and type(self.current[0]) is type(request_id) and self.current[0]==request_id:
                self.current[1].cancelled.set()

    def close(self):
        with self.lock:
            current=self.current
            if current:current[1].cancelled.set()
        if current:current[2].join(timeout=6)
