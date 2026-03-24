cd server
start cmd /k python server.py
start cmd /k python http_server.py
cd ..
cd login
start /k fix_qrc.bat
start cmd /k python login.py