import time, socket

print("--- testing TCP connection to dynamodb:8000 ---")
t0 = time.time()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(("dynamodb", 8000))
    print("TCP connect took", round(time.time() - t0, 3), "s")
except Exception as e:
    print("TCP FAILED:", type(e).__name__, e)
    raise SystemExit(1)
finally:
    s.close()

print()
print("--- sending raw HTTP POST ---")
t0 = time.time()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(("dynamodb", 8000))
body = '{"Limit": 10}'
req = (
    "POST / HTTP/1.1\r\n"
    "Host: dynamodb:8000\r\n"
    "Content-Type: application/x-amz-json-1.0\r\n"
    "X-Amz-Target: DynamoDB_20120810.ListTables\r\n"
    "Content-Length: " + str(len(body)) + "\r\n"
    "\r\n"
    + body
)
s.sendall(req.encode())
try:
    data = s.recv(4096)
    print("got", len(data), "bytes in", round(time.time() - t0, 3), "s")
    print("first 200 bytes:", data[:200])
except socket.timeout:
    print("TIMED OUT after 5s - server never responded")
finally:
    s.close()
