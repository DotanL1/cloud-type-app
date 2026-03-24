import time
import json
import secrets
import os

SESS_FILE = "sessions.json"
LOCK_FILE = "sessions.lock"
SESSION_TIMEOUT = 30


class session:
    @staticmethod
    def _load_locked():
        return session.read_sessions()

    @staticmethod
    def _save_locked(data):
        session.write_sessions(data)

    @staticmethod
    def time_session(session_id):
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s["session_id"] == session_id:
                    s["last_seen"] = time.time()
            session._save_locked(data)
        finally:
            session.release_lock()

        
    @staticmethod
    def check_timeout():
        while True:
            session.acquire_lock()
            try:
                data = session._load_locked()
                data["sessions"] = [
                    s for s in data["sessions"]
                    if time.time() - s["last_seen"] <= SESSION_TIMEOUT
                ]
                session._save_locked(data)
            finally:
                session.release_lock()
            time.sleep(SESSION_TIMEOUT/3)

    @staticmethod
    def add_token(session_id,token):
        session.add_open_token(session_id, token, {})

    @staticmethod
    def add_open_token(session_id, token, payload):
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s['session_id'] == session_id:
                    s.setdefault('tokens', {})
                    s['tokens'][token] = payload or {}
                    s['Token'] = token
            session._save_locked(data)
        finally:
            session.release_lock()

    @staticmethod
    def remove_token(session_id):
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s['session_id'] == session_id:
                    s['Token'] = ''
                    s['tokens'] = {}
            session._save_locked(data)
        finally:
            session.release_lock()

    @staticmethod
    def search_for_token(token):
        result = session.consume_open_token(token)
        return result["session_id"] if result else None

    @staticmethod
    def consume_open_token(token):
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                tokens = s.get('tokens', {})
                if token in tokens:
                    payload = tokens.pop(token)
                    if s.get('Token') == token:
                        s['Token'] = ''
                    session._save_locked(data)
                    return {
                        "session_id": s['session_id'],
                        "username": s['username'],
                        "payload": payload or {}
                    }
                if s.get('Token') == token:
                    s['Token'] = ''
                    session._save_locked(data)
                    return {
                        "session_id": s['session_id'],
                        "username": s['username'],
                        "payload": {}
                    }
        finally:
            session.release_lock()
            

    @staticmethod
    def write_sessions(data):
        with open(SESS_FILE, "w") as f:
            json.dump(data, f, indent=4)

    def read_sessions():
        if not os.path.exists(SESS_FILE):
            return {"sessions": []}

        with open(SESS_FILE, "r") as f:
            return json.load(f)




    @staticmethod
    def add_session(username, source):
        session.acquire_lock()

        data = session.read_sessions()

        session_id = secrets.token_hex(16)

        data["sessions"].append({
            "username": username,
            "session_id": session_id,
            "source": source,
            "last_seen" : time.time(),
            "Token" : '',
            "page_token": "",
            "tokens": {}
        })

        session.write_sessions(data)

        session.release_lock()

        return session_id

    
            

    @staticmethod
    def remove_session(session_id):

        session.acquire_lock()
        try:
            data = session._load_locked()
            data["sessions"] = [
                s for s in data["sessions"]
                if s["session_id"] != session_id
            ]
            session._save_locked(data)
        finally:
            session.release_lock()

    @staticmethod
    def is_logged_in(session_id):

        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s["session_id"] == session_id:
                    return s["username"]
        finally:
            session.release_lock()

        return None


    @staticmethod
    def set_page_token(session_id):
        """
        Generate a fresh page_token for this session, overwriting any previous one.
        Call this every time a new browser page opens docs.html.
        Returns the new token.
        """
        token = secrets.token_hex(16)
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s["session_id"] == session_id:
                    s["page_token"] = token
            session._save_locked(data)
        finally:
            session.release_lock()
        return token

    @staticmethod
    def validate_page_token(session_id, page_token):
        """
        Returns True only if page_token matches what is stored for this session.
        A mismatch means a newer page has since opened and taken over.
        """
        session.acquire_lock()
        try:
            data = session._load_locked()
            for s in data["sessions"]:
                if s["session_id"] == session_id:
                    return s.get("page_token", "") == page_token
        finally:
            session.release_lock()
        return False

    @staticmethod
    def acquire_lock():
        while True:
            try:
                fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                return
            except FileExistsError:
                time.sleep(0.05)
    @staticmethod
    def release_lock():
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
