from binaryninja import *
_locals = locals().copy()
_locals.update({m: __import__(m) for m in (
    'os', 're', 'sys',
)})

import SocketServer
import gc
import io
import json
import logging
import os
import rlcompleter
import signal
import socket
import sys
import threading
import traceback
from code import InteractiveConsole

class StdoutWriter(io.IOBase):
    def __init__(self, shell): self.shell = shell
    def write(self, b): return self.shell.output(b)
    def writable(self): return True

class InteractiveServer(SocketServer.BaseRequestHandler):
    def handle(self):
        old = sys.stdout
        olderr = sys.stderr
        try:
            shell = Shell(self.request)
            sys.stdout = StdoutWriter(shell) # io.TextIOWrapper(io.BufferedWriter(StdoutWriter(shell)), line_buffering=True, encoding='utf8')
            shell.interact()
        except SystemExit:
            pass
        finally:
            sys.stdout = old
            sys.stderr = olderr

class Shell(InteractiveConsole):
    def __init__(self, s):
        self.s = s
        self.buf = s.makefile('r', bufsize=1)
        self.outbuf = []
        self.reset_count = 0
        InteractiveConsole.__init__(self)
        self.locals.update(_locals)
        self.completer = rlcompleter.Completer(self.locals)
        self._interpreter = None

    @property
    def interpreter(self):
        if not self._interpreter:
            obj = [o for o in gc.get_objects() if isinstance(o, scriptingprovider.PythonScriptingInstance.InterpreterThread)]
            if obj:
                self._interpreter = obj[0]
        return self._interpreter

    def traceback(self):
        self.write(traceback.format_exc())

    def copy_to_repl(self):
        try:
            ip = self.interpreter
            if ip:
                self.locals.update({
                    'write_at_cursor': ip.write_at_cursor,
                    'get_selected_data': ip.get_selected_data,
                    'bv': ip.current_view,
                    'current_view': ip.current_view,
                    'current_function': ip.current_func,
                    'current_basic_block': ip.current_block,
                    'current_address': ip.current_addr,
                    'here': ip.current_selection_begin,
                    'current_selection': (ip.current_selection_begin, ip.current_selection_end),
                })
                if ip.current_func is None:
                    self.locals['current_llil'] = None
                    self.locals['current_mlil'] = None
                else:
                    self.locals['current_llil'] = ip.current_func.low_level_il
                    self.locals['current_mlil'] = ip.current_func.medium_level_il
        except Exception:
            self.traceback()

    def copy_from_repl(self):
        try:
            ip = self.interpreter
            if ip:
                move = None
                if self.locals['here'] != ip.current_addr:
                    move = self.locals['here']
                elif self.locals['current_address'] != ip.current_addr:
                    move = self.locals['current_address']
                if move and ip.current_view and ip.current_view.file:
                    if not ip.current_view.file.navigate(ip.current_view.file.view, move):
                        self.write('navigation to {:#x} failed'.format(move))
        except Exception:
            self.traceback()

    def write(self, data):
        try:
            self.send('print', text=data)
        except IOError:
            logging.info(traceback.format_exc())
            raise SystemExit

    def output(self, b):
        self.outbuf.append(b.decode('utf8'))
        return len(b)

    def recv(self):
        line = self.buf.readline().decode('utf8')
        if not line: return None
        return json.loads(line)

    def send(self, cmd, **kwargs):
        kwargs['cmd'] = cmd
        self.s.send((json.dumps(kwargs) + '\n').encode('utf8'))

    def prompt(self, prompt):
        if self.outbuf:
            self.send('print', text=''.join(self.outbuf))
            self.outbuf = []
        self.send('prompt', prompt=prompt)

    def interact(self):
        self.copy_to_repl()
        ps1 = '>>> '
        ps2 = '... '
        self.write('Python {} on {})\n'.format(sys.version, sys.platform))
        self.prompt(ps1)
        while True:
            m = self.recv()
            if not m:
                self.send('exit')
                break
            cmd = m['cmd']
            if cmd == 'input':
                self.reset_count = 0
                self.copy_to_repl()
                more = self.push(m['text'])
                self.copy_from_repl()
                if more:
                    self.prompt(ps2)
                else:
                    self.prompt(ps1)
            elif cmd == 'complete':
                self.send('completion', text=self.completer.complete(m['text'], m['state']))
            elif cmd == 'reset':
                if self.buffer:
                    self.resetbuffer()
                    self.prompt(ps1)
                else:
                    self.reset_count += 1
                    if self.reset_count >= 2:
                        self.send('exit')
                        break
                    self.prompt(ps1)

path = os.path.expanduser('~/.bn_repl.sock')
if os.path.exists(path):
    os.unlink(path)
SocketServer.UnixStreamServer.allow_reuse_address = True
server = SocketServer.UnixStreamServer(path, InteractiveServer)
t = threading.Thread(target=server.serve_forever)
t.daemon = True
t.start()
