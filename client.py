import atexit
import json
import os
import readline
import rlcompleter
import socket
import sys

py3 = sys.version_info[0] >= 3
if not py3:
    input = raw_input

libedit = 'libedit' in readline.__doc__
if libedit:
    readline.parse_and_bind('bind ^I rl_complete')
else:
    readline.parse_and_bind('tab: complete')
    readline.parse_and_bind('set completion-ignore-case on')
    readline.parse_and_bind('set show-all-if-ambiguous on')

histfile = os.path.expanduser('~/.bn_repl_history')
if os.path.exists(histfile):
    try:
        readline.read_history_file(histfile)
    except IOError:
        pass
    readline.set_history_length(1000)

atexit.register(readline.write_history_file, histfile)

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(os.path.expanduser('~/.bn_repl.sock'))
if py3:
    sin = s.makefile('r', buffering=1, encoding='utf8')
else:
    sin = s.makefile('r', bufsize=1)

def send(cmd, **m):
    m['cmd'] = cmd
    s.send((json.dumps(m) + '\n').encode('utf8'))

def recv():
    line = sin.readline()
    if not py3:
        line = line.decode('utf8')
    return json.loads(line)

def complete(text, state):
    if not text:
        readline.insert_text('    ')
        return None
    send('complete', text=text, state=state)
    text = recv()['text']
    return text

readline.set_completer(complete)

while True:
    m = recv()
    cmd = m['cmd']
    if cmd == 'prompt':
        prompt = m['prompt']
        try:
            line = input(prompt)
            send('input', text=line + '\n')
        except KeyboardInterrupt:
            send('reset')
        except EOFError:
            s.shutdown(socket.SHUT_RDWR)
            break
    elif cmd == 'print':
        print(m['text'].rstrip('\n'))
    elif cmd == 'exit':
        break
print
