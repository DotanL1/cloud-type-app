import socket
from secure_channel import SecureChannel
import threading
import sql_orm
import hashlib
import os
import base64
import json
from pathlib import Path
from sessions import session
import secrets
import time
from file_locking import file_guard

db = sql_orm.user_orm()
SESSION_TIMEOUT = 30

SESS_FILE = "sessions.json"
LOCK_FILE = "sessions.lock"
CHUNK_SIZE = 32768 #4096*4

def hash_pass(data,salt=b''):
    return hashlib.sha256(data.encode()+salt).hexdigest()


def handle_signup(username,email,password):
    salt = os.urandom(16)
    try:
        os.makedirs(f'.\\files\\{username}')
    except FileExistsError:
        pass
    finally:
        ok = db.insert_user(username,email,hash_pass(password,salt),salt,f'{username}')
        if ok:
            return 'SGOK||'
        return 'SGFL||'
    


def handle_login(username,password):
    user = db.get_user(username)
    if user:
        print(user)
        hash_password = user[1]
        salt = user[2]
        home_path = user[3]
    
        if hash_pass(password,salt) == hash_password:
            sess_id = session.add_session(username,'Application')
            return f'LGOK||{home_path}||{username}||{sess_id}'
    return 'LGFL||'


def get_owned_file_entries(home_path):
    db.sync_owned_files(home_path)
    return db.list_owned_files(home_path)


def handle_list_files(home_path):
    names = [entry["name"] for entry in get_owned_file_entries(home_path)]
    return 'LRES||' + '||'.join(names)


def resolve_file_access(requester, owner, filename, required_access='view'):
    if requester == owner:
        return True, 'owner'
    access = db.get_file_share_access(owner, filename, requester)
    if not access:
        return False, None
    if required_access == 'edit' and access != 'edit':
        return False, access
    return True, access


def build_file_path(owner, filename):
    return f'.\\files\\{owner}\\{filename}'


def handle_shared_files(username):
    payload = db.list_shared_with_user(username)
    return 'SHLS||' + json.dumps(payload)


def handle_file_send(filename, owner, chunk_num):
    path = build_file_path(owner, filename)
    ext = Path(path).suffix.lower()
    with file_guard(owner, Path(filename).stem, ext):
        f = open(path, 'rb')
        try:
            f.seek(int(chunk_num) * CHUNK_SIZE,0)
            chunk = f.read(CHUNK_SIZE)
        finally:
            f.close()
    if not chunk:
        return f'FINI||{ext}'
    base64encoded = base64.b64encode(chunk).decode('ascii')
    return f'CHUN||{base64encoded}||{filename}||{owner}'


def parse_owner_and_file(parts, owner_idx, file_idx, fallback_owner):
    owner = parts[owner_idx].strip() if len(parts) > owner_idx else ''
    filename = parts[file_idx].strip() if len(parts) > file_idx else ''
    return (owner or fallback_owner), filename


def handle_share(owner, file_name, recipient, access_level):
    db.sync_owned_files(owner)
    ok, message = db.share_file_with_user(owner, file_name, recipient, access_level)
    if not ok:
        return f'SHFL||{message}'
    return f'SHOK||{message}'


def handle_unshare(owner, file_name, recipient):
    if db.remove_file_share(owner, file_name, recipient):
        return f'UNOK||Removed access for {recipient}.'
    return 'UNFL||Share entry was not found.'



def handle_client(cli_sock,addr):
    chan = SecureChannel(cli_sock)
    chan.handshake('dh',i_am_initiator=True)
    authed_home = None
    r_u_alive = threading.Thread(target=check_if_alive,args=(chan,),daemon=True)
    r_u_alive.start()
    while True:
        try:
            info = chan.recv().decode()
            parts = info.split('||')
            code = parts[0]
            reply = None
            if code == 'ALIV':
                session.time_session(parts[1])

            elif code == 'SIGU':
                reply = handle_signup(parts[1],parts[2],parts[3])

            elif code == 'LOGN':
                reply = handle_login(parts[1],parts[2])
                if reply.startswith('LGOK||'):
                    authed_home = reply.split('||')[1]  
            elif code == 'LIST':
                if not session.is_logged_in(parts[1]):
                    reply = 'NOAU||Not authenticated'
                else:
                    reply = handle_list_files(authed_home)
            elif code == 'LSHS':
                user = session.is_logged_in(parts[1])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    reply = handle_shared_files(user)
            elif code == 'DELT':
                user = session.is_logged_in(parts[2])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    path = build_file_path(user, parts[1])
                    if os.path.exists(path):
                        ext = Path(parts[1]).suffix.lower()
                        with file_guard(user, Path(parts[1]).stem, ext):
                            if os.path.exists(path):
                                os.remove(path)
                        db.remove_file(user, parts[1])
                    reply = handle_list_files(authed_home)

            elif code == 'DOWN':
                user = session.is_logged_in(parts[4] if len(parts) > 4 else parts[3])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    owner, file_name = parse_owner_and_file(parts, 1, 2, authed_home)
                    chunk_num = parts[3] if len(parts) > 4 else parts[2]
                    ok, _access = resolve_file_access(user, owner, file_name, 'view')
                    if not ok:
                        reply = 'NOAU||Not authorized'
                    else:
                        reply = handle_file_send(file_name, owner, chunk_num)
            elif code == 'CONN':
                if not session.is_logged_in(parts[1]):
                    reply = 'NOAU||Not authenticated'
                else:
                    token = secrets.token_urlsafe(32)
                    session.add_token(parts[1],token)
                    reply = f'CONN||{token}'
            elif code == 'OPEN':
                user = session.is_logged_in(parts[3] if len(parts) > 3 else parts[2])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    owner, file_name = parse_owner_and_file(parts, 1, 2, authed_home)
                    ok, access = resolve_file_access(user, owner, file_name, 'view')
                    if not ok:
                        reply = 'NOAU||Not authorized'
                        continue
                    token = secrets.token_urlsafe(32)
                    payload = {
                        "owner": owner,
                        "file": file_name,
                        "access": access,
                        "type": Path(file_name).suffix.lower()
                    }
                    session.add_open_token(parts[3] if len(parts) > 3 else parts[2], token, payload)
                    reply = f'OPEN||{token}||{file_name}||{owner}||{access}'
            elif code == 'SHAR':
                user = session.is_logged_in(parts[4])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    reply = handle_share(user, parts[1], parts[2], parts[3])
            elif code == 'UNSH':
                user = session.is_logged_in(parts[3])
                if not user:
                    reply = 'NOAU||Not authenticated'
                else:
                    reply = handle_unshare(user, parts[1], parts[2])
            

            



            elif code == 'EXIT':
                session.remove_session(parts[1])
                reply = 'EXIT||'

            if reply:
                chan.send(reply)
        except Exception as e:
            print(e.args)
            print(e)
            continue




def check_if_alive(channel):
    while True:
        try:
            channel.send("RUAL||")
            time.sleep(SESSION_TIMEOUT/3)
        except OSError:
            return
        except ConnectionResetError:
            return
        

def get_files(folder):
    lst = []
    folder_path = Path(folder)
    for file in folder_path.iterdir():
        if file.is_file():
            lst.append(folder+file.name)
    return lst

def main():
    srv_sock = socket.socket()
    srv_sock.bind(('127.0.0.1',1234))
    srv_sock.listen()
    while True:
        cli_sock,addr = srv_sock.accept()
        t = threading.Thread(target=handle_client, args=(cli_sock, addr))
        t.start()
















if __name__ == '__main__':
    main()
