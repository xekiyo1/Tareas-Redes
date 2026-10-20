import argparse, random, select, threading, time
from CongestionControl import SocketTCP

class Wire(SocketTCP):
    def wrap_data_as_segment(self, d, seq): return f"{seq}|".encode() + d
    def wrap_ack_as_segment(self, ack): return f"{ack}|".encode()
    def parse_segment(self, s):
        h, d = s.split(b"|", 1); return {"SEQ": int(h), "ACK": int(h), "DATA": d}
    def divide_message(self, m, n): return [m[i:i+n] for i in range(0, len(m), n)]
    def recv_using_go_back_n(self, n):
        if not getattr(self, "_left", b""):
            full = getattr(SocketTCP, "_receive_full_message", None) or SocketTCP.recv_using_go_back_n
            self._left = full(self, n)
        c, self._left = self._left[:n], self._left[n:]
        return c

class Lossy:
    def __init__(s, sock, rate): s.sock, s.rate, s.sent, s.dropped = sock, rate, 0, 0
    def sendto(s, data, addr):
        s.sent += 1
        if random.random() < s.rate: s.dropped += 1; return len(data)
        return s.sock.sendto(data, addr)
    def __getattr__(s, n): return getattr(s.sock, n)

def pair(port, loss, timeout, cc, debug):
    a_s, a_c = ("127.0.0.1", port), ("127.0.0.1", port + 1)
    srv, cli = Wire(0, 0, a_c, 1024, 8), Wire(0, 0, a_s, 1024, 8)
    srv.socketUDP.bind(a_s); cli.socketUDP.bind(a_c)
    for x in (srv, cli): x.socketUDP.socket_udp = Lossy(x.socketUDP.socket_udp, loss)
    cli.timeout, cli.congestion_control_on, cli.debug = timeout, cc, debug
    return srv, cli

def drain(srv, stop):
    s = srv.socketUDP.socket_udp
    while not stop.is_set():
        if select.select([s], [], [], 0.05)[0]:
            s.recvfrom(1024)
            srv.socketUDP.sendto(srv.wrap_ack_as_segment(srv.ack), srv.destination_address)

def recv_all(srv, n):
    got = b""
    while len(got) < n: got += srv.recv(1024, mode="go_back_n")
    return got

def check(name, ok): print(f"{name}: {'Passed' if ok else 'Failed'}")

def tests(a):
    srv, cli = pair(a.port, a.loss, a.timeout, a.cc == "on", a.debug)
    LONG, M, stop = bytes(i % 251 for i in range(1500)), b"Mensaje de largo 19", threading.Event()
    def server():
        check("Test 1", srv.recv(16, mode="go_back_n") == b"Mensje de len=16")
        check("Test 2", srv.recv(19, mode="go_back_n") == M)
        p1 = srv.recv(14, mode="go_back_n"); p2 = srv.recv(14, mode="go_back_n")
        check("Test 3", p1 + p2 == M)
        check("Test 4 (1500 B)", recv_all(srv, len(LONG)) == LONG)
        drain(srv, stop)
    t = threading.Thread(target=server); t.start()
    for m in (b"Mensje de len=16", M, M, LONG): cli.send(m, mode="go_back_n")
    time.sleep(0.5); stop.set(); t.join()
    s = cli.socketUDP.socket_udp
    print(f"Cliente: enviados={s.sent}, descartados={s.dropped}")

def run(cc, a, port):
    payload = bytes(i % 251 for i in range(a.size))
    srv, cli = pair(port, a.loss, a.timeout, cc, a.debug)
    res, stop = {}, threading.Event()
    def rx(): res["d"] = recv_all(srv, a.size); drain(srv, stop)
    t = threading.Thread(target=rx); t.start()
    t0 = time.perf_counter(); cli.send(payload, mode="go_back_n"); dt = time.perf_counter() - t0
    stop.set(); t.join()
    s = cli.socketUDP.socket_udp
    return dt, s.sent, s.dropped, res.get("d") == payload

def experiment(a):
    rows, port = {True: [], False: []}, 9000
    for r in range(1, a.runs + 1):
        for cc in ((True, False) if a.cc == "both" else (a.cc == "on",)):
            dt, sent, drop, ok = run(cc, a, port); port += 2
            rows[cc].append((dt, sent, drop))
            print(f"run {r} | CC {'on ' if cc else 'off'} | {dt:6.2f} s | enviados={sent} | descartados={drop} | integridad={'OK' if ok else 'FALLÓ'}")
    print("\nPromedios")
    for cc, v in rows.items():
        if v: print(f"CC {'on ' if cc else 'off'}: tiempo={sum(x[0] for x in v)/len(v):.2f} s | enviados={sum(x[1] for x in v)/len(v):.1f} | descartados={sum(x[2] for x in v)/len(v):.1f}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--exp", action="store_true"); p.add_argument("--cc", choices=["on", "off", "both"], default=None)
    p.add_argument("--loss", type=float, default=0.0); p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--size", type=int, default=1500); p.add_argument("--runs", type=int, default=1)
    p.add_argument("--debug", action="store_true"); p.add_argument("--seed", type=int); p.add_argument("--port", type=int, default=5000)
    a = p.parse_args()
    a.cc = a.cc or ("both" if a.exp else "on")
    if a.seed is not None: random.seed(a.seed)
    experiment(a) if a.exp else tests(a)