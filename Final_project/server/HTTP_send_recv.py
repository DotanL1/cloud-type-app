DEBUG_HTTP = False



def http_recv(sock, BLOCK_SIZE = 8192):
    data = b''
    rnrn_pos = -1
    while rnrn_pos == -1:
        _d = sock.recv(BLOCK_SIZE)
        if _d == b'':
            return b'',None  # header none and body none
        data += _d
        rnrn_pos = data.find(b'\r\n\r\n')
    rnrn_pos += 4
    body =b''
    if b'Content-Length: '  in data[:rnrn_pos]:
        len_pos = data[:rnrn_pos].find(b'Content-Length: ') + 16
        len_pos2 = data[len_pos:rnrn_pos].find(b'\r\n') + len_pos
        body_size = int(data[len_pos:len_pos2])
        if len(data) > rnrn_pos:
            body = data[rnrn_pos:]
        while len(body) <  body_size:
            _d = sock.recv(min(BLOCK_SIZE,body_size - len(body)))
            if _d == b'':
                return b'',None  # header none and body none
            body += _d
    if DEBUG_HTTP:
       print ('\nRECV-' +str(len(data[:rnrn_pos]) + len(body)) +'<<<',data[:rnrn_pos],' \tBody(first 100): ',body[:100])
       pass
    return data[:rnrn_pos] , body




def http_send(sock, status="200 OK", headers=None, body=b''):
    if headers is None:
        headers = {}
        
    response = f'HTTP/1.1 {status}\r\n'
    
    if body and 'Content-Length' not in headers:
        headers['Content-Length'] = str(len(body))
        
    for key, value in headers.items():
        response += f'{key}: {value}\r\n'
    
    response += '\r\n'
    
    if DEBUG_HTTP:
        print ('\nSEND--->',len(response + body),'>>> ',response, body)
        pass
    sock.sendall(response.encode() + body)

