import sqlite3
import time
import os




class User(object):
    def __init__(self,username,email,password_hash,salt,home_path):
        self.username = username
        self.email = email
        self.password = password_hash
        self.salt = salt
        self.home_path = home_path









class user_orm(object):
    def __init__(self, db_file='User.db'):
        self.conn = None
        self.cur = None
        self.db_file = db_file
        self.create_tables()




    def open_DB(self):
        self.conn = sqlite3.connect(self.db_file)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.cur = self.conn.cursor()

    def close_DB(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cur = None

    def commit(self):
        if self.conn:
            self.conn.commit()

    def create_tables(self): 
        self.open_DB()
        self.cur.execute(
        'CREATE TABLE IF NOT EXISTS user('
        'username TEXT PRIMARY KEY, '
        'email TEXT, '
        'password_hash TEXT,' 
        'salt TEXT,' 
        'home_path TEXT)'
        )
        self.cur.execute(
        'CREATE TABLE IF NOT EXISTS file_entry('
        'owner_username TEXT NOT NULL, '
        'file_name TEXT NOT NULL, '
        'created_at REAL NOT NULL, '
        'PRIMARY KEY(owner_username, file_name), '
        'FOREIGN KEY(owner_username) REFERENCES user(username) ON DELETE CASCADE)'
        )
        self.cur.execute(
        'CREATE TABLE IF NOT EXISTS file_share('
        'owner_username TEXT NOT NULL, '
        'file_name TEXT NOT NULL, '
        'recipient_username TEXT NOT NULL, '
        'access_level TEXT NOT NULL, '
        'created_at REAL NOT NULL, '
        'PRIMARY KEY(owner_username, file_name, recipient_username), '
        'FOREIGN KEY(owner_username) REFERENCES user(username) ON DELETE CASCADE, '
        'FOREIGN KEY(recipient_username) REFERENCES user(username) ON DELETE CASCADE)'
        )
    
        self.commit()
        self.close_DB()




    def insert_user(self,username, email, password_hash,salt,home_path):
        self.open_DB()
        try:
            exists = self.cur.execute(
                "SELECT 1 FROM user WHERE username=?",
                (username,)
            ).fetchone()
            if exists:
                return False

            self.cur.execute(
                "INSERT INTO user( username, email, password_hash, salt,home_path) "
                "VALUES ( ?, ?, ?, ?, ?)",
                (username,email,password_hash,salt,home_path)
            )
            self.commit()
            return True
        finally:
            self.close_DB()
    
    def get_user(self, username):
        self.open_DB()
        row = self.cur.execute(
            "SELECT email, password_hash, salt, home_path FROM user WHERE username=?",
            (username,)
        ).fetchone()
        self.close_DB()
        return row
    
    def get_home_path(self, username):
        self.open_DB()
        try:
            row = self.cur.execute(
                "SELECT home_path FROM user WHERE username=?",
                (username,)
            ).fetchone()
            return row[0] if row else None
        finally:
            self.close_DB()

    def user_exists(self, username):
        self.open_DB()
        try:
            row = self.cur.execute(
                "SELECT 1 FROM user WHERE username=?",
                (username,)
            ).fetchone()
            return bool(row)
        finally:
            self.close_DB()

    def upsert_file(self, owner_username, file_name):
        self.open_DB()
        try:
            self.cur.execute(
                "INSERT INTO file_entry(owner_username, file_name, created_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(owner_username, file_name) DO NOTHING",
                (owner_username, file_name, time.time())
            )
            self.commit()
            return True
        finally:
            self.close_DB()

    def remove_file(self, owner_username, file_name):
        self.open_DB()
        try:
            self.cur.execute(
                "DELETE FROM file_share WHERE owner_username=? AND file_name=?",
                (owner_username, file_name)
            )
            self.cur.execute(
                "DELETE FROM file_entry WHERE owner_username=? AND file_name=?",
                (owner_username, file_name)
            )
            self.commit()
            return self.cur.rowcount > 0
        finally:
            self.close_DB()

    def file_exists(self, owner_username, file_name):
        self.open_DB()
        try:
            row = self.cur.execute(
                "SELECT 1 FROM file_entry WHERE owner_username=? AND file_name=?",
                (owner_username, file_name)
            ).fetchone()
            return bool(row)
        finally:
            self.close_DB()

    def list_owned_files(self, owner_username):
        self.open_DB()
        try:
            rows = self.cur.execute(
                "SELECT file_name FROM file_entry WHERE owner_username=? ORDER BY file_name",
                (owner_username,)
            ).fetchall()
            return [
                {
                    "name": row[0],
                    "owner": owner_username,
                    "access": "owner"
                }
                for row in rows
            ]
        finally:
            self.close_DB()

    def sync_owned_files(self, owner_username):
        folder = os.path.join('.', 'files', owner_username)
        disk_files = set()
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    disk_files.add(name)

        self.open_DB()
        try:
            rows = self.cur.execute(
                "SELECT file_name FROM file_entry WHERE owner_username=?",
                (owner_username,)
            ).fetchall()
            db_files = {row[0] for row in rows}

            for file_name in disk_files - db_files:
                self.cur.execute(
                    "INSERT INTO file_entry(owner_username, file_name, created_at) VALUES (?, ?, ?)",
                    (owner_username, file_name, time.time())
                )

            stale_files = db_files - disk_files
            for file_name in stale_files:
                self.cur.execute(
                    "DELETE FROM file_share WHERE owner_username=? AND file_name=?",
                    (owner_username, file_name)
                )
                self.cur.execute(
                    "DELETE FROM file_entry WHERE owner_username=? AND file_name=?",
                    (owner_username, file_name)
                )

            self.commit()
            return sorted(disk_files)
        finally:
            self.close_DB()

    def upsert_file_share(self, owner_username, file_name, recipient_username, access_level):
        self.open_DB()
        try:
            self.cur.execute(
                "INSERT INTO file_share(owner_username, file_name, recipient_username, access_level, created_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(owner_username, file_name, recipient_username) DO UPDATE SET "
                "access_level=excluded.access_level, created_at=excluded.created_at",
                (owner_username, file_name, recipient_username, access_level, time.time())
            )
            self.commit()
            return True
        finally:
            self.close_DB()

    def share_file_with_user(self, owner_username, file_name, recipient_username, access_level):
        if recipient_username == owner_username:
            return False, 'You already own this file.'
        if access_level not in ('view', 'edit'):
            return False, 'Invalid access level.'
        if not self.user_exists(recipient_username):
            return False, 'Recipient username was not found.'
        if not self.file_exists(owner_username, file_name):
            return False, 'File was not found.'
        self.upsert_file_share(owner_username, file_name, recipient_username, access_level)
        return True, f'Shared {file_name} with {recipient_username} as {access_level}.'

    def remove_file_share(self, owner_username, file_name, recipient_username):
        self.open_DB()
        try:
            self.cur.execute(
                "DELETE FROM file_share WHERE owner_username=? AND file_name=? AND recipient_username=?",
                (owner_username, file_name, recipient_username)
            )
            self.commit()
            return self.cur.rowcount > 0
        finally:
            self.close_DB()

    def list_shared_with_user(self, username):
        self.open_DB()
        try:
            rows = self.cur.execute(
                "SELECT fs.owner_username, fs.file_name, fs.access_level, fs.created_at "
                "FROM file_share fs "
                "JOIN file_entry fe ON fe.owner_username = fs.owner_username AND fe.file_name = fs.file_name "
                "WHERE fs.recipient_username=? "
                "ORDER BY fs.owner_username, fs.file_name",
                (username,)
            ).fetchall()
            return [
                {
                    "owner": row[0],
                    "file_name": row[1],
                    "access": row[2],
                    "created_at": row[3]
                }
                for row in rows
            ]
        finally:
            self.close_DB()

    def list_file_recipients(self, owner_username, file_name):
        self.open_DB()
        try:
            rows = self.cur.execute(
                "SELECT fs.recipient_username, fs.access_level, fs.created_at "
                "FROM file_share fs "
                "JOIN file_entry fe ON fe.owner_username = fs.owner_username AND fe.file_name = fs.file_name "
                "WHERE fs.owner_username=? AND fs.file_name=? "
                "ORDER BY fs.recipient_username",
                (owner_username, file_name)
            ).fetchall()
            return [
                {
                    "recipient": row[0],
                    "access": row[1],
                    "created_at": row[2]
                }
                for row in rows
            ]
        finally:
            self.close_DB()

    def get_file_share_access(self, owner_username, file_name, username):
        self.open_DB()
        try:
            row = self.cur.execute(
                "SELECT access_level FROM file_share "
                "WHERE owner_username=? AND file_name=? AND recipient_username=?",
                (owner_username, file_name, username)
            ).fetchone()
            return row[0] if row else None
        finally:
            self.close_DB()
