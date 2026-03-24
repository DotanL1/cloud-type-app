import socket
import threading
import ssl
import os
import json
import base64
import hashlib
import struct
from urllib.parse import parse_qs, unquote_plus
from HTTP_send_recv import http_recv, http_send
from sessions import session
import sql_orm
import mammoth
import pypandoc
from file_locking import file_guard

pypandoc.download_pandoc()
db = sql_orm.user_orm()
PATH_TO_FILES = ".\\http_files\\"

CERT_FILE = "server.crt"
KEY_FILE = "server.key"
ROOMS = {}
ROOMS_LOCK = threading.Lock()


def get_file_data(filename):
    with open(filename, 'rb') as f:
        return f.read()


def get_content_type(filename):
    extension = filename.lower().split('.')[-1]
    content_types = {
        'ico': 'image/x-icon',
        'html': 'text/html',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
        'css': 'text/css',
        'js': 'application/javascript'
    }
    return content_types.get(extension, 'application/octet-stream')


def get_file_type_from_name(file_name):
    lower = file_name.lower()
    if lower.endswith('.docx'):
        return 'doc'
    if lower.endswith('.pptx'):
        return 'slide'
    if lower.endswith('.png'):
        return 'whiteboard'
    return 'doc'


def get_storage_path(owner, file_name):
    return os.path.join(f'.\\files\\{owner}', file_name)


def normalize_owner(raw_owner):
    if raw_owner is None:
        return None
    owner = unquote_plus(raw_owner).strip()
    return owner or None


def get_query_owner(query):
    qs = parse_qs(query, keep_blank_values=True)
    owners = qs.get('owner', [])
    return normalize_owner(owners[0]) if owners else None


def can_access_file(session_id, owner, file_name, required_access='view'):
    username = session.is_logged_in(session_id)
    if not username:
        return None, None
    if username == owner:
        return username, 'owner'
    access = db.get_file_share_access(owner, file_name, username)
    if not access:
        return username, None
    if required_access == 'edit' and access != 'edit':
        return username, access
    return username, access


def get_resolved_file(query, expected_ext, session_id, required_access='view'):
    file_name = get_query_file_name(query, expected_ext)
    owner = get_query_owner(query) or session.is_logged_in(session_id)
    if not file_name or not owner:
        return None
    full_name = f'{file_name}{expected_ext}'
    username, access = can_access_file(session_id, owner, full_name, required_access)
    if not username or not access:
        return None
    return {
        "owner": owner,
        "user": username,
        "access": access,
        "file_name": file_name,
        "full_name": full_name
    }


def _room_key(owner, file_name, file_type):
    return (owner, file_name, file_type)


def get_room(owner, file_name, file_type, loader):
    key = _room_key(owner, file_name, file_type)
    with ROOMS_LOCK:
        room = ROOMS.get(key)
        if room is None:
            room = {
                "state": None,
                "version": 0,
                "clients": {},
                "lock": threading.Lock(),
                "timer": None,
                "dirty": False,
                "persist_error": ""
            }
            ROOMS[key] = room
    with room["lock"]:
        if room["state"] is None:
            room["state"] = loader(owner, file_name)
    return room


def schedule_room_persist(owner, file_name, file_type, saver, delay=1.0):
    room = get_room(owner, file_name, file_type, lambda o, f: load_state_from_disk(o, f, file_type))
    with room["lock"]:
        room["dirty"] = True
        if room["timer"]:
            room["timer"].cancel()
        timer = threading.Timer(delay, persist_room_state, args=(owner, file_name, file_type, saver))
        timer.daemon = True
        room["timer"] = timer
        timer.start()


def persist_room_state(owner, file_name, file_type, saver):
    room = get_room(owner, file_name, file_type, lambda o, f: load_state_from_disk(o, f, file_type))
    with room["lock"]:
        state = room["state"]
        room["timer"] = None
    try:
        saver(owner, file_name, state)
        with room["lock"]:
            room["dirty"] = False
            room["persist_error"] = ""
    except Exception as exc:
        with room["lock"]:
            room["persist_error"] = str(exc)
        broadcast_room(owner, file_name, file_type, {
            "type": "persist_error",
            "message": str(exc)
        })


def broadcast_room(owner, file_name, file_type, payload, skip_client=None):
    room = get_room(owner, file_name, file_type, lambda o, f: load_state_from_disk(o, f, file_type))
    with room["lock"]:
        clients = list(room["clients"].items())
    dead_clients = []
    for client_id, client in clients:
        if skip_client and client_id == skip_client:
            continue
        try:
            send_ws_json(client["sock"], payload)
        except Exception:
            dead_clients.append(client_id)
    if dead_clients:
        with room["lock"]:
            for client_id in dead_clients:
                room["clients"].pop(client_id, None)


def not_found(sock):
    body = b'404 Not Found'
    http_send(
        sock,
        headers={
            "Content-Type": "text/html",
            "Content-Length": str(len(body)),
            "Connection": "close"
        },
        body=body
    )


def internalerror(sock):
    error_message = b"500 Internal Server Error"
    http_send(
        sock,
        headers={
            "Content-Type": "text/html",
            "Content-Length": str(len(error_message)),
            "Connection": "close"
        },
        body=error_message
    )


def validate_http(request):
    if request.startswith('GET'):
        return 'GET-request'
    elif request.startswith('POST'):
        return 'POST-request'
    return 'ERROR'


def split_request_path(path):
    clean_path, _, query = path.partition('?')
    request = PATH_TO_FILES + 'index.html' if clean_path == '/' else clean_path[1:]
    return request, query


def normalize_file_name(raw_name, expected_ext=None):
    if raw_name is None:
        return None
    name = unquote_plus(raw_name).strip()
    if not name:
        return None
    name = name.replace('\\', '/').split('/')[-1].strip()
    if expected_ext and name.lower().endswith(expected_ext.lower()):
        name = name[:-len(expected_ext)]
    return name or None


def get_query_file_name(query, expected_ext=None):
    qs = parse_qs(query, keep_blank_values=True)
    candidates = qs.get('file', [])
    raw_name = candidates[0] if candidates else query
    return normalize_file_name(raw_name, expected_ext)


def ws_accept_value(key):
    magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    digest = hashlib.sha1((key + magic).encode('utf-8')).digest()
    return base64.b64encode(digest).decode('ascii')


def recv_ws_frame(sock):
    head = sock.recv(2)
    if len(head) < 2:
        raise ConnectionError('WebSocket disconnected')
    opcode = head[0] & 0x0F
    masked = (head[1] & 0x80) != 0
    length = head[1] & 0x7F
    if length == 126:
        length = struct.unpack('!H', sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack('!Q', sock.recv(8))[0]
    mask = sock.recv(4) if masked else b''
    payload = b''
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise ConnectionError('WebSocket disconnected')
        payload += chunk
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    if opcode == 0x8:
        raise ConnectionError('WebSocket close frame')
    if opcode == 0x9:
        send_ws_frame(sock, payload, opcode=0xA)
        return recv_ws_frame(sock)
    return opcode, payload


def send_ws_frame(sock, payload, opcode=0x1):
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    header = bytearray()
    header.append(0x80 | opcode)
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack('!H', length))
    else:
        header.append(127)
        header.extend(struct.pack('!Q', length))
    sock.sendall(bytes(header) + payload)


def send_ws_json(sock, payload):
    send_ws_frame(sock, json.dumps(payload))


def handle_get_req(sock, headers, data,session_id):
    http_parts = headers.split(' ')
    path = http_parts[1]
    request, query = split_request_path(path)
    endpoint = request
    print([request, query] if query else [request])
    print(headers)
    # Handle dynamic document/slides/whiteboard open endpoints before serving static files
    if endpoint == 'open_doc':
        resolved = get_resolved_file(query, '.docx', session_id, 'view')
        if not resolved:
            http_send(sock,headers={
                "Location": "/http_files/index.html",
                "Connection" : "close"
            },
            status='303 See Other')
            return
        open_doc(sock, resolved["owner"], resolved["file_name"])
        return
    if endpoint == 'open_slide':
        resolved = get_resolved_file(query, '.pptx', session_id, 'view')
        if not resolved:
            http_send(sock,headers={
                "Location": "/http_files/index.html",
                "Connection" : "close"
            },
            status='303 See Other')
            return
        open_slide(sock, resolved["owner"], resolved["file_name"])
        return
    if endpoint == 'open_whiteboard':
        resolved = get_resolved_file(query, '.png', session_id, 'view')
        if not resolved:
            http_send(sock,headers={
                "Location": "/http_files/index.html",
                "Connection" : "close"
            },
            status='303 See Other')
            return
        open_whiteboard(sock, resolved["owner"], resolved["file_name"])
        return
    if path != '/':
        # Handle token-based login for choose.html, docs.html, slides.html and whitboard.html
        if query and 'token=' in query:
            qs = parse_qs(query, keep_blank_values=True)
            token_list = qs.get('token', [])
            file_list = qs.get('file', [])
            if token_list:
                if session_id:
                    session.remove_session(session_id)
                token_info = session.consume_open_token(token_list[0])
                if token_info:
                    sess = token_info["session_id"]
                    payload = token_info.get("payload", {})
                    # If a file is specified and we're targeting docs.html/slides.html/whitboard.html, redirect there.
                    target_headers = {
                        "Connection": "close",
                        "Set-Cookie": f"session_id={sess}; HttpOnly; Secure; Path=/"
                    }
                    target_file = payload.get("file") or (file_list[0] if file_list else "")
                    owner = payload.get("owner", "")
                    access = payload.get("access", "")
                    suffix = f"?file={target_file}&owner={owner}&access={access}"
                    if request.endswith('docs.html') and target_file:
                        target = f"/http_files/docs.html{suffix}"
                    elif request.endswith('slides.html') and target_file:
                        target = f"/http_files/slides.html{suffix}"
                    elif request.endswith('whitboard.html') and target_file:
                        target = f"/http_files/whitboard.html{suffix}"
                    else:
                        set_cookie(sock, sess)
                        return
                    target_headers["Location"] = target
                    http_send(
                        sock,
                        headers=target_headers,
                        status='303 See Other'
                    )
                    return
        if session.is_logged_in(session_id):
            pass
        else:
            request = PATH_TO_FILES + 'index.html'
    else:
        if session.is_logged_in(session_id):
            http_send(sock,headers={
            "Location": "/http_files/choose.html",
            "Connection" : "close"
            },
            status='303 See Other')

    if os.path.exists(request):
        show_html_file(sock, request)
    else:
        not_found(sock)


def get_session_id(http_parts :list):
    for i in http_parts:
        if i.startswith('session_id'):
            return i.split('=')[1].strip()
    return None



def handle_post_req(sock, headers, data,session_id):
    http_parts = headers.split(' ')
    path = http_parts[1]
    request, query = split_request_path(path)
    endpoint = request
    print(headers)
    if path != '/' and os.path.exists(request):
        if session.is_logged_in(session_id):
            pass
        else:
            http_send(sock,headers={
            "Location": "/http_files/index.html",
            "Connection" : "close"
        },
        status='303 See Other'
        )
            return
    else:
        pass
    
    print(request)
    print([request, query] if query else [request])
    print(endpoint)
    if request.endswith('index.html'):
        if session_id:
            session.remove_session(session_id)
        handle_login(sock, data.decode())

    elif request.endswith('logout'):
        session.remove_session(session_id)

    elif endpoint == 'save_doc':
        resolved = get_resolved_file(query, '.docx', session_id, 'edit')
        if not resolved:
            http_send(sock, status='403 Forbidden', headers={"Connection": "close"})
            return
        data = data.decode()
        print('Saving file')
        file_saving(sock, data, resolved["owner"], resolved["file_name"])
    elif endpoint == 'save_slide':
        resolved = get_resolved_file(query, '.pptx', session_id, 'edit')
        if not resolved:
            http_send(sock, status='403 Forbidden', headers={"Connection": "close"})
            return
        data = data.decode()
        print('Saving slide deck')
        file_saving_slide(sock, data, resolved["owner"], resolved["file_name"])
    elif endpoint == 'save_whiteboard':
        # For whiteboard, we accept saves without per-page displacement checks
        # to keep the protocol simple: any authenticated session may save.
        resolved = get_resolved_file(query, '.png', session_id, 'edit')
        if not resolved:
            http_send(sock, status='403 Forbidden', headers={"Connection": "close"})
            return
        data = data.decode()
        print('Saving whiteboard')
        if not resolved["file_name"]:
            error_body = json.dumps({"error": "Missing whiteboard file name"}).encode('utf-8')
            http_send(
                sock,
                status='400 Bad Request',
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(error_body)),
                    "Connection": "close"
                },
                body=error_body
            )
            return
        try:
            save_info = file_saving_whiteboard(data, resolved["owner"], resolved["file_name"])
        except ValueError as exc:
            error_body = json.dumps({"error": str(exc)}).encode('utf-8')
            http_send(
                sock,
                status='400 Bad Request',
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(error_body)),
                    "Connection": "close"
                },
                body=error_body
            )
            return
        body = json.dumps(save_info).encode('utf-8')
        http_send(
            sock,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(body)),
                "Connection": "close"
            },
            body=body
        )
    else:
        not_found(sock)
def file_saving(sock,data,owner,file_name):
    http_send(sock,headers= {
        "Connection" : "close"
    })
    data = data.strip()
    print('Saving FILE')
    folder = f'.\\files\\{owner}'
    os.makedirs(folder, exist_ok=True)
    with file_guard(owner, file_name, '.docx'):
        pypandoc.convert_text(data,'docx',format='html',outputfile=f'{folder}\\{file_name}.docx')
    db.upsert_file(owner, f'{file_name}.docx')


def file_saving_slide(sock, data, owner, file_name):
    http_send(sock,headers= {
        "Connection" : "close"
    })
    data = data.strip()
    print('Saving SLIDE')
    folder = f'.\\files\\{owner}'
    os.makedirs(folder, exist_ok=True)
    with file_guard(owner, file_name, '.pptx'):
        pypandoc.convert_text(data,'pptx',format='html',outputfile=f'{folder}\\{file_name}.pptx')
    db.upsert_file(owner, f'{file_name}.pptx')


def file_saving_whiteboard(data, owner, file_name):
    # data is expected to be a data URL: "data:image/png;base64,...."
    data = data.strip()
    if not data:
        raise ValueError("Whiteboard body is empty")
    print('Saving WHITEBOARD')
    folder = f'.\\files\\{owner}'
    os.makedirs(folder, exist_ok=True)
    prefix = "data:image/png;base64,"
    if data.startswith(prefix):
        b64 = data[len(prefix):]
    else:
        b64 = data
    try:
        png_bytes = base64.b64decode(b64.encode('ascii'), validate=True)
    except Exception as exc:
        raise ValueError("Whiteboard body is not valid PNG data") from exc
    path = os.path.join(folder, f'{file_name}.png')
    print(f'Writing WHITEBOARD {path} ({len(png_bytes)} bytes)')
    with file_guard(owner, file_name, '.png'):
        with open(path, 'wb') as f:
            f.write(png_bytes)
    db.upsert_file(owner, f'{file_name}.png')
    return {
        "ok": True,
        "file": f'{file_name}.png',
        "bytes_written": len(png_bytes)
    }


def open_doc(sock, owner, file_name):
    path = os.path.join(f'.\\files\\{owner}', f'{file_name}.docx')
    if not os.path.exists(path):
        not_found(sock)
        return
    with file_guard(owner, file_name, '.docx'):
        with open(path, 'rb') as docx_file:
            result = mammoth.convert_to_html(docx_file)
    html_content = result.value.encode('utf-8')
    http_send(
        sock,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(html_content)),
            "Connection": "close"
        },
        body=html_content
    )


def open_slide(sock, owner, file_name):
    path = os.path.join(f'.\\files\\{owner}', f'{file_name}.pptx')
    if not os.path.exists(path):
        # If the slideshow doesn't exist yet, return empty content so the
        # client starts from a blank deck instead of showing a 404 page.
        empty = b""
        http_send(
            sock,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": str(len(empty)),
                "Connection": "close"
            },
            body=empty
        )
        return
    # Use pandoc to convert PPTX to HTML
    with file_guard(owner, file_name, '.pptx'):
        html = pypandoc.convert_file(path, 'html')
    html_content = html.encode('utf-8')
    http_send(
        sock,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(html_content)),
            "Connection": "close"
        },
        body=html_content
    )


def open_whiteboard(sock, owner, file_name):
    path = os.path.join(f'.\\files\\{owner}', f'{file_name}.png')
    if not os.path.exists(path):
        # If the whiteboard image doesn't exist yet, return empty body so client starts blank.
        empty = b""
        print(f'Opening WHITEBOARD {path} (missing)')
        http_send(
            sock,
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(empty)),
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Connection": "close"
            },
            body=empty
        )
        return
    with file_guard(owner, file_name, '.png'):
        with open(path, 'rb') as f:
            png_bytes = f.read()
    print(f'Opening WHITEBOARD {path} ({len(png_bytes)} bytes)')
    http_send(
        sock,
        headers={
            "Content-Type": "image/png",
            "Content-Length": str(len(png_bytes)),
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close"
        },
        body=png_bytes
    )


def load_state_from_disk(owner, file_name, file_type=None):
    file_type = file_type or get_file_type_from_name(file_name)
    base_name = normalize_file_name(file_name) or file_name
    if file_type == 'doc':
        path = get_storage_path(owner, f'{base_name}.docx')
        if not os.path.exists(path):
            return ""
        with file_guard(owner, base_name, '.docx'):
            with open(path, 'rb') as docx_file:
                return mammoth.convert_to_html(docx_file).value
    if file_type == 'slide':
        path = get_storage_path(owner, f'{base_name}.pptx')
        if not os.path.exists(path):
            return ""
        with file_guard(owner, base_name, '.pptx'):
            return pypandoc.convert_file(path, 'html')
    path = get_storage_path(owner, f'{base_name}.png')
    if not os.path.exists(path):
        return ""
    with file_guard(owner, base_name, '.png'):
        with open(path, 'rb') as f:
            png_bytes = f.read()
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode('ascii')


def save_state_to_disk(owner, file_name, file_type, state):
    base_name = normalize_file_name(file_name) or file_name
    if file_type == 'doc':
        folder = f'.\\files\\{owner}'
        os.makedirs(folder, exist_ok=True)
        with file_guard(owner, base_name, '.docx'):
            pypandoc.convert_text(state or "", 'docx', format='html', outputfile=f'{folder}\\{base_name}.docx')
        return
    if file_type == 'slide':
        folder = f'.\\files\\{owner}'
        os.makedirs(folder, exist_ok=True)
        with file_guard(owner, base_name, '.pptx'):
            pypandoc.convert_text(state or "", 'pptx', format='html', outputfile=f'{folder}\\{base_name}.pptx')
        return
    file_saving_whiteboard(state or "", owner, base_name)

def show_html_file(sock, request, page_token=None):
    file_content = get_file_data(request)
    # If serving docs.html or slides.html, inject the page_token as a JS variable so the
    # page can send it back with every save request.
    if page_token and (request.endswith('docs.html') or request.endswith('slides.html')):
        injection = f'<script>const PAGE_TOKEN = "{page_token}";</script>\n</head>'.encode()
        file_content = file_content.replace(b'</head>', injection, 1)
    content_type = get_content_type(request)

    http_send(
        sock,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(file_content)),
            "Connection": "close"
        },
        body=file_content
    )


def hash_pass(data, salt=b''):
    return hashlib.sha256(data.encode() + salt).hexdigest()


def handle_login(sock, data):
    username = (data.split('&')[0]).split('=')[1]
    password = (data.split('&')[1]).split('=')[1]

    user = db.get_user(username)
    if not user:
        show_html_file(sock, PATH_TO_FILES + 'index.html')
        return

    hash_password = user[1]
    salt = user[2]

    if hash_pass(password, salt) == hash_password:
        session_id = session.add_session(username, 'Web App')
        set_cookie(sock,session_id)
        return

    show_html_file(sock, PATH_TO_FILES + 'index.html')


def set_cookie(sock,session_id):
    http_send(sock,headers={
           "Location" : '/http_files/choose.html',
           "Connection" : "close",
           "Set-Cookie" : f"session_id={session_id}; HttpOnly; Secure; Path=/"
        },
        status='303 See Other'
    )


def handle_collab_websocket(sock, headers, session_id):
    request_line = headers.split('\r\n', 1)[0]
    path = request_line.split(' ')[1]
    request, query = split_request_path(path)
    if request != 'collab_ws':
        not_found(sock)
        return

    qs = parse_qs(query, keep_blank_values=True)
    owner = get_query_owner(query) or session.is_logged_in(session_id)
    file_name = unquote_plus(qs.get('file', [''])[0]).strip()
    file_type = qs.get('type', [get_file_type_from_name(file_name)])[0]
    ext_map = {'doc': '.docx', 'slide': '.pptx', 'whiteboard': '.png'}
    full_name = file_name if os.path.splitext(file_name)[1] else f'{file_name}{ext_map.get(file_type, "")}'
    username, access = can_access_file(session_id, owner, full_name, 'view')
    if not username or not access:
        http_send(sock, status='403 Forbidden', headers={"Connection": "close"})
        return

    ws_key = ''
    for line in headers.split('\r\n'):
        if line.lower().startswith('sec-websocket-key:'):
            ws_key = line.split(':', 1)[1].strip()
            break
    if not ws_key:
        http_send(sock, status='400 Bad Request', headers={"Connection": "close"})
        return

    accept_value = ws_accept_value(ws_key)
    sock.sendall((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_value}\r\n\r\n"
    ).encode('utf-8'))

    room = get_room(owner, file_name, file_type, lambda o, f: load_state_from_disk(o, f, file_type))
    client_id = session_id + ':' + base64.urlsafe_b64encode(os.urandom(6)).decode('ascii')
    with room["lock"]:
        room["clients"][client_id] = {
            "sock": sock,
            "session_id": session_id,
            "username": username,
            "access": access
        }
        current_state = room["state"]
        version = room["version"]
        persist_error = room["persist_error"]
    send_ws_json(sock, {
        "type": "hello",
        "clientId": client_id,
        "owner": owner,
        "file": file_name,
        "fileType": file_type,
        "access": access,
        "version": version,
        "state": current_state,
        "persistError": persist_error
    })

    try:
        while True:
            opcode, payload = recv_ws_frame(sock)
            if opcode != 0x1:
                continue
            message = json.loads(payload.decode('utf-8'))
            if message.get("type") != "update":
                continue
            if access not in ('owner', 'edit'):
                send_ws_json(sock, {"type": "error", "message": "Read-only access"})
                continue
            new_state = message.get("state", "")
            with room["lock"]:
                room["state"] = new_state
                room["version"] += 1
                version = room["version"]
            schedule_room_persist(owner, file_name, file_type, save_state_to_disk, 1.0 if file_type != 'whiteboard' else 0.5)
            broadcast_room(owner, file_name, file_type, {
                "type": "update",
                "clientId": client_id,
                "version": version,
                "state": new_state
            }, skip_client=client_id)
            send_ws_json(sock, {"type": "ack", "version": version})
    except Exception:
        pass
    finally:
        with room["lock"]:
            room["clients"].pop(client_id, None)

def handle_client(sock, addr):
    try:
        headers, data = http_recv(sock)
        if not headers:
            sock.close()
            return

        headers = headers.decode(errors='ignore')
        session_id = get_session_id(headers.split(' '))
        if session_id:
            session.time_session(session_id)
        if 'Upgrade: websocket' in headers:
            handle_collab_websocket(sock, headers, session_id)
            return
        http_req = validate_http(headers)
        

        if http_req == 'GET-request':
            handle_get_req(sock, headers, data,session_id)
        elif http_req == 'POST-request':
            handle_post_req(sock, headers, data,session_id)
        else:
            sock.close()
    except Exception as e:
        raise
        try:
            internalerror(sock)
        except:
            pass
    finally:
        sock.close()


def main():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('127.0.0.1', 443))
    server_sock.listen()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    t = threading.Thread(target=session.check_timeout,daemon=True)
    t.start()


    while True:
        client_sock, addr = server_sock.accept()
        try:
            tls_sock = context.wrap_socket(client_sock, server_side=True)
            t = threading.Thread(target=handle_client, args=(tls_sock, addr))
            t.start()
        except Exception as e:
            client_sock.close()


if __name__ == '__main__':
    main()
