import sys
from PySide6.QtCore import QObject, Slot,Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
import resources_rc
import socket
from secure_channel import SecureChannel
import threading
import base64
from pathlib import Path
import webbrowser
import secrets


CURRENT_DOWNLOAD_PATH = None
CURRENT_DOWNLOAD_CHUNK = 0
CURRENT_DOWNLOAD_OWNER = None

class Backend(QObject):
    login_res = Signal(bool,str)

    sigunp_res = Signal(bool,str)

    cloud_list_res = Signal(list)
    shared_list_res = Signal(list)
    action_status = Signal(bool, str)

    log_out = Signal()

    def __init__(self):
        super().__init__()
        self.sock = socket.socket()
        self.http_sock = socket.socket()
        self.chan = None
        self.home_path = None
        self.username = None
        self.session_id = None
        self.connectToServer()

        

    def connectToServer(self,host='127.0.0.1',port=1234):
        try:
            self.sock.connect((host,port))
            self.chan = SecureChannel(self.sock)
            self.chan.handshake('dh',i_am_initiator=False)
            t = threading.Thread(target=self.recv_loop,daemon=True)
            t.start()
        except:
            raise




    
    def recv_loop(self):
        global CURRENT_USERNAME
        try:
            while True:
                try:
                    data = self.chan.recv().decode()
                    parts = data.split('||')
                    code = parts[0]
                except:
                    raise
                

                if code == 'RUAL':
                    self.chan.send(f'ALIV||{self.session_id}')

                elif code == 'LGOK':
                    self.home_path = parts[1] if len(parts) > 1 else None
                    self.username = parts[2] if len(parts) > 2 else None
                    self.session_id = parts[3] if len(parts) >3 else None
                    if not self.home_path:
                        raise 'No homepath found'
                    if not self.username:
                        raise 'Error Logging in Username doesn\'t exist'
                    if not self.session_id:
                        raise 'Server didn\'t send session id'
                    self.login_res.emit(True,'')

                elif code =='LGFL':
                    self.login_res.emit(False,"Wrong username/password")

                elif code == 'SGOK':
                    self.sigunp_res.emit(True,'')

                elif code == 'SGFL':
                    self.sigunp_res.emit(False,'Sign up Failed')

                elif code == 'LRES':
                    files = parts[1:] if len(parts) > 1 else []
                    self.cloud_list_res.emit(files)
                elif code == 'SHLS':
                    payload = []
                    if len(parts) > 1 and parts[1]:
                        try:
                            import json
                            payload = json.loads(parts[1])
                        except Exception:
                            payload = []
                    self.shared_list_res.emit(payload)
                elif code == 'CHUN':
                    self.handle_file_download(parts[1],parts[2])
                elif code == 'FINI':
                    self.end_file_download(parts[1])
                elif code == 'CONN':
                    self.connect_to_http(parts[1])
                elif code == 'OPEN':
                    owner = parts[3] if len(parts) > 3 else self.username
                    access = parts[4] if len(parts) > 4 else "owner"
                    self.open_file_http(parts[1], parts[2], owner, access)
                elif code in ('SHOK', 'UNOK'):
                    self.action_status.emit(True, parts[1] if len(parts) > 1 else '')
                elif code in ('SHFL', 'UNFL', 'NOAU'):
                    self.action_status.emit(False, parts[1] if len(parts) > 1 else 'Action failed')

                elif code == 'EXIT':
                    self.home_path = None
                    self.username = None
                    self.session_id = None
                    self.log_out.emit()

        except Exception as e:
            raise

    

    def open_file_http(self,token,file,owner,access):
        # Open the specific document, slideshow or whiteboard in the browser with a one-time HTTP token.
        # HTTP server will validate the token, set the cookie, and then redirect
        # to the appropriate editor so the user is authenticated even if this is
        # their first HTTP request.
        lower = file.lower()
        if lower.endswith(".png"):
            url = f"https://127.0.0.1/http_files/whitboard.html?token={token}&file={file}&owner={owner}&access={access}"
        elif lower.endswith(".pptx"):
            url = f"https://127.0.0.1/http_files/slides.html?token={token}&file={file}&owner={owner}&access={access}"
        else:
            url = f"https://127.0.0.1/http_files/docs.html?token={token}&file={file}&owner={owner}&access={access}"
        webbrowser.open(url)


    def end_file_download (self,file_ext):
        global CURRENT_DOWNLOAD_CHUNK
        global CURRENT_DOWNLOAD_PATH
        global CURRENT_DOWNLOAD_OWNER
        pre_ext = Path(CURRENT_DOWNLOAD_PATH)
        pre_ext.rename(pre_ext.with_suffix(file_ext))
        CURRENT_DOWNLOAD_CHUNK = 0
        CURRENT_DOWNLOAD_PATH = None
        CURRENT_DOWNLOAD_OWNER = None
        

    def handle_file_download(self,chunk,filename):
        global CURRENT_DOWNLOAD_CHUNK
        global CURRENT_DOWNLOAD_OWNER
        print(CURRENT_DOWNLOAD_PATH)
        with open (CURRENT_DOWNLOAD_PATH,'ab') as f:
            chunk_bytes = base64.b64decode(chunk.encode('ascii'))
            f.write(chunk_bytes)
        self.chan.send(f'DOWN||{CURRENT_DOWNLOAD_OWNER}||{filename}||{CURRENT_DOWNLOAD_CHUNK}||{self.session_id}')
        CURRENT_DOWNLOAD_CHUNK +=1

    def connect_to_http(self,token):
        url = f"https://127.0.0.1/http_files/choose.html?token={token}"
        webbrowser.open(url)

    @Slot(str,str)
    def login(self,username,password):
        self.chan.send(f'LOGN||{username}||{password}')
    
    @Slot(str,str,str)
    def signup(self,username,email,password):
        self.chan.send(f'SIGU||{username}||{email}||{password}')

    @Slot(str,str)
    def downloadCloudFile(self,file,full_path):
        self.downloadCloudFileByOwner(file, full_path, self.username or "")

    @Slot(str,str,str)
    def downloadCloudFileByOwner(self,file,full_path,owner):
        global CURRENT_DOWNLOAD_PATH
        global CURRENT_DOWNLOAD_CHUNK
        global CURRENT_DOWNLOAD_OWNER
        print (f'!!!!!! {file},{full_path}')
        CURRENT_DOWNLOAD_PATH = full_path
        CURRENT_DOWNLOAD_OWNER = owner
        self.chan.send(f'DOWN||{owner}||{file}||{CURRENT_DOWNLOAD_CHUNK}||{self.session_id}')
        CURRENT_DOWNLOAD_CHUNK += 1

    @Slot()
    def requestCloudFiles(self):
        self.chan.send(f'LIST||{self.session_id}')

    @Slot()
    def requestSharedFiles(self):
        self.chan.send(f'LSHS||{self.session_id}')

    @Slot()
    def ask_connect_to_http(self):
        self.chan.send(f'CONN||{self.session_id}')

    @Slot(str)
    def delete_file(self,file_name):
        self.chan.send(f'DELT||{file_name}||{self.session_id}')

    @Slot(str)
    def open_file(self,file_name):
        self.open_file_by_owner(file_name, self.username or "")

    @Slot(str, str)
    def open_file_by_owner(self,file_name,owner):
        self.chan.send(f'OPEN||{owner}||{file_name}||{self.session_id}')

    @Slot(str, str, str)
    def share_file(self, file_name, recipient, access):
        self.chan.send(f'SHAR||{file_name}||{recipient}||{access}||{self.session_id}')

    @Slot(str, str)
    def unshare_file(self, file_name, recipient):
        self.chan.send(f'UNSH||{file_name}||{recipient}||{self.session_id}')
    
    @Slot()
    def exit_app(self):
        self.chan.send(f'EXIT||{self.session_id}')


def main():
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    backend = Backend() 
    engine.rootContext().setContextProperty("Backend", backend)  

    engine.load("qrc:/login.qml")
    if not engine.rootObjects():
        sys.exit(-1)

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
