import os

WELCOME_FILE = os.path.join(os.path.dirname(__file__), "welcome.txt")

def proxy(data):
    fno = os.open(WELCOME_FILE, os.O_RDONLY) 
    return {
            "file": fno,
            "reply": "HTTP/1.1 200 OK\r\n\r\n"
           }
