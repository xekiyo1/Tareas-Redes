"""Prueba de integración: levanta los 5 routers con MTU y envía paquetes reales por UDP.

Ejecutar: python3 test_integracion.py     (usa los puertos 8881..8885)
"""

import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTS = {n: 8880 + n for n in range(1, 6)}
procs, logs = {}, {}


def start_network():
    for n, port in PORTS.items():
        path = os.path.join(AQUI, f"_R{n}.log")
        logs[n] = path
        procs[n] = subprocess.Popen(
            [sys.executable, "-u", "router.py", "127.0.0.1", str(port), f"rutas/rutas_R{n}_v3_mtu.txt"],
            cwd=AQUI, stdout=open(path, "w"), stderr=subprocess.STDOUT)
    time.sleep(1.0)


def stop_network():
    for p in procs.values():
        p.terminate()
    for p in procs.values():
        p.wait()
    for path in logs.values():
        if os.path.exists(path):
            os.remove(path)


def log(n):
    with open(logs[n], encoding="utf-8") as f:
        return f.read()


def printed_lines(n):
    """Líneas que el router imprimió como mensaje (excluye debug/forwarding/etc.)."""
    skip = ("[", "redirigiendo", "No hay rutas", "Se recibió")
    return [l for l in log(n).splitlines() if l and not l.startswith(skip)]


def send(*args):
    subprocess.run([sys.executable, "enviar_mensaje.py", *map(str, args)], cwd=AQUI,
                   check=True, stdout=subprocess.DEVNULL)


def wait_for(cond, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def expected(text, total):
    payload = total - 16
    return ((text.encode() * (payload // len(text.encode()) + 1))[:payload]).decode()


def check(name, ok):
    print(("OK   " if ok else "FALLA"), name)
    if not ok:
        raise SystemExit(f"Falló: {name}")


def main():
    start_network()
    try:
        # 1) paquete chico (no se fragmenta): R1 -> R5
        send("127.0.0.1", 8885, 10, "127.0.0.1", 8881, "hola!", "--id", 347)
        check("paquete chico R1->R5 llega", wait_for(lambda: "hola!" in printed_lines(5)))

        # 2) 8 paquetes de 150 bytes R1 -> R5 (fragmenta y re-fragmenta; round-robin en R2/R3/R4)
        msgs = {}
        for i in range(8):
            txt = f"#{i}-"
            msgs[i] = expected(txt, 150)
            send("127.0.0.1", 8885, 64, "127.0.0.1", 8881, txt, "--id", 100 + i, "--total", 150)
            time.sleep(0.05)
        ok = wait_for(lambda: all(printed_lines(5).count(m) == 1 for m in msgs.values()), 8)
        check("8 paquetes de 150 bytes R1->R5 reensamblados (1 vez cada uno)", ok)
        check("hubo fragmentación y re-fragmentación en R1/R2",
              "fragmentando" in log(1) and "fragmentando" in log(2))

        # 3) distintos orígenes: R5 -> R1 (entrando por R5) y R4 -> R2
        m_a, m_b = expected("<A>", 150), expected("<B>", 150)
        send("127.0.0.1", 8881, 64, "127.0.0.1", 8885, "<A>", "--id", 500, "--total", 150)
        send("127.0.0.1", 8882, 64, "127.0.0.1", 8884, "<B>", "--id", 501, "--total", 150)
        check("150 bytes R5->R1", wait_for(lambda: m_a in printed_lines(1)))
        check("150 bytes R4->R2", wait_for(lambda: m_b in printed_lines(2)))

        # 4) UTF-8 multibyte cortado en medio de un carácter
        utf = "ñandú✓"
        send("127.0.0.1", 8885, 64, "127.0.0.1", 8881, utf, "--id", 600, "--total", 150)
        utf_exp = (utf.encode() * 40)[:134].decode("utf-8", errors="replace")
        check("UTF-8 fragmentado en medio de un carácter", wait_for(lambda: utf_exp in printed_lines(5)))

        # 5) TTL: con TTL=1 de R1 a R3 el paquete muere en R2
        send("127.0.0.1", 8883, 1, "127.0.0.1", 8881, "no-debe-llegar", "--id", 700)
        check("TTL=1 R1->R3 se descarta en R2", wait_for(lambda: "con TTL 0" in log(2)))
        check("TTL=1: R3 no imprime el mensaje", "no-debe-llegar" not in printed_lines(3))

        # 6) fragmentos enviados a mano (2 IDs) en distintos órdenes, directo a R5
        for modo in ("orden", "desorden", "intercalado", "mezcla"):
            before = len(printed_lines(5))
            subprocess.run([sys.executable, "prueba_fragmentos.py", "127.0.0.1", "8885",
                            "127.0.0.1", "8885", "50", modo], cwd=AQUI, check=True,
                           stdout=subprocess.DEVNULL)
            e1 = ("Mensaje-del-paquete-101|" * 10)[:100]
            e2 = ("Mensaje-del-paquete-202|" * 10)[:100]
            check(f"fragmentos manuales modo '{modo}'",
                  wait_for(lambda: printed_lines(5)[before:].count(e1) == 1
                                   and printed_lines(5)[before:].count(e2) == 1))

        # 7) archivo línea por línea con ID distinto por línea
        subprocess.run([sys.executable, "prueba_router.py", "127.0.0.1;8885;20", "127.0.0.1", "8881",
                        "archivo_prueba.txt"], cwd=AQUI, check=True, stdout=subprocess.DEVNULL)
        lines = [f"linea 0{i}" for i in range(1, 6)]
        check("archivo línea por línea (5 líneas)",
              wait_for(lambda: all(printed_lines(5).count(l) == 1 for l in lines)))
        print("\nTodas las pruebas de integración pasaron.")
    finally:
        stop_network()


if __name__ == "__main__":
    main()
