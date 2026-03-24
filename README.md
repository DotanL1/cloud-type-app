# cloud-type-app
# ☁️ Secure Cloud Storage & Collaboration System

A full-stack secure cloud storage application that supports **encrypted communication, file management, sharing, and real-time collaboration**.

---

## 🚀 Features

### 🔐 Secure Communication

* End-to-end encrypted channel using:

  * Diffie-Hellman key exchange
  * AES-CBC encryption
  * HMAC authentication (Encrypt-then-MAC)
* Custom secure socket wrapper (`SecureChannel`)
* Protection against tampering and replay attacks

---

### 👤 Authentication & Sessions

* User signup & login system
* Password hashing with salt (SHA-256)
* Session management with expiration
* Token-based file access (for HTTP open)

---

### 📁 Cloud File System

* Upload, download, and list files
* Chunked file transfer (efficient for large files)
* Per-user storage directories
* File metadata stored in SQLite

---

### 🤝 File Sharing

* Share files with other users
* Permission levels:

  * `view`
  * `edit`
* Access control enforced on both TCP and HTTP layers

---

### 🌐 HTTP File Access & Editing

* Lightweight HTTP server for:

  * Viewing files in browser
  * Editing documents
* Supports:

  * `.docx` → HTML conversion (via `mammoth`)
  * `.pptx` handling
* Session validation for secure access

---

### 🧠 Real-Time Collaboration

* In-memory “rooms” for shared files
* Version tracking
* Delayed persistence (auto-save)
* Multi-user editing support

---

### 🔒 Concurrency & Locking

* File-level locking mechanism (`file_guard`)
* Prevents race conditions during read/write
* Works across threads and processes

---

### 💻 Client Application (Qt / QML)

* GUI built with **PySide6 + QML**
* Features:

  * Login / Signup UI
  * File browser
  * Shared files view
  * Download / open actions
* Communicates with server over secure channel

---

## 🧱 Architecture

Client (Qt/QML)
⬇ SecureChannel (AES + HMAC)
TCP Server (commands & logic)
⬇
HTTP Server (file access & editing)
⬇
SQLite Database + File Storage

---

## 📦 Project Structure

```
.
├── server.py              # Main TCP server
├── http_server.py        # HTTP server for file access
├── secure_channel.py     # Encrypted communication layer
├── crypto_utils.py       # AES + HMAC utilities
├── tcp_by_size.py        # Custom TCP framing
├── sessions.py           # Session management
├── sql_orm.py            # SQLite ORM
├── file_locking.py       # File locking system
├── HTTP_send_recv.py     # HTTP parsing/sending
├── login.py              # Client backend (Qt bridge)
├── login.qml             # GUI frontend
```

---

## 🔐 Security Design

* **Key Exchange:** Diffie-Hellman
* **Encryption:** AES-CBC
* **Integrity:** HMAC-SHA256
* **Transport:** Custom framed TCP protocol
* **Sessions:** Token-based + timeout cleanup

---

## ⚙️ How to Run

### 1. Install dependencies

```bash
pip install pyside6 cryptography pycryptodome mammoth pypandoc
```

### 2. Run server

```bash
python server.py
```

### 3. Run HTTP server

```bash
python http_server.py
```

### 4. Run client

```bash
python login.py
```

---


## 📚 Notes

This project demonstrates:

* Network programming (TCP + HTTP)
* Applied cryptography
* Concurrency & synchronization
* Full-stack system design

---
