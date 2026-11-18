"""Envía a mano los fragmentos de 2 datagramas (ID 101 y 202) para probar el reensamblaje.

Uso:
    python3 prueba_fragmentos.py <IP_dest> <Puerto_dest> <IP_envio> <Puerto_envio> <MTU> <modo>

Modos:
    orden        todos los fragmentos del ID 101 y luego todos los del 202, en orden
    desorden     igual, pero cada lista en orden inverso
    intercalado  alterna fragmentos de ambos IDs
    mezcla       todos los fragmentos de ambos IDs en orden aleatorio

Ejemplo (se envía directo al router destino R5, que debe imprimir los 2 mensajes completos):
    python3 prueba_fragmentos.py 127.0.0.1 8885 127.0.0.1 8885 50 intercalado
"""

import random
import socket
import sys

from router import create_packet, fragment_IP_packet


def main():
    if len(sys.argv) != 7:
        print(__doc__)
        sys.exit(1)

    dest_ip, dest_port = sys.argv[1], int(sys.argv[2])
    send_addr = (sys.argv[3], int(sys.argv[4]))
    mtu, modo = int(sys.argv[5]), sys.argv[6]

    lists = []
    for pkt_id in (101, 202):
        text = (f"Mensaje-del-paquete-{pkt_id}|" * 10)[:100]
        pkt = create_packet({"ip": dest_ip, "port": dest_port, "ttl": 10,
                             "id": pkt_id, "offset": 0, "flag": 0, "message": text})
        lists.append(fragment_IP_packet(pkt, mtu))
        print(f"ID {pkt_id}: {len(lists[-1])} fragmentos (MTU={mtu}); mensaje esperado: {text}")

    a, b = lists
    if modo == "orden":
        seq = a + b
    elif modo == "desorden":
        seq = a[::-1] + b[::-1]
    elif modo == "intercalado":
        seq = [x for pair in zip(a, b) for x in pair] + a[len(b):] + b[len(a):]
    elif modo == "mezcla":
        seq = a + b
        random.shuffle(seq)
    else:
        print("Modo inválido")
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for frag in seq:
        sock.sendto(frag, send_addr)
    sock.close()
    print(f"{len(seq)} fragmentos enviados a {send_addr} en modo '{modo}'.")


if __name__ == "__main__":
    main()
