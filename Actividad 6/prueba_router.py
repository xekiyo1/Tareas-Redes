"""Envía un archivo línea por línea (un datagrama por línea, cada uno con ID distinto).

Uso:
    python3 prueba_router.py "<IP;Puerto;TTL>" <IP_router_inicial> <puerto_router_inicial> [archivo]

Ejemplo (de R1 a R5):
    python3 prueba_router.py "127.0.0.1;8885;10" 127.0.0.1 8881 archivo_prueba.txt

En bash hay que comillar los headers (si no, ';' separa comandos). Las líneas vacías se omiten.
"""

import socket
import sys

from router import create_packet


def main():
    if len(sys.argv) < 4:
        print('Uso: python3 prueba_router.py "<IP;Puerto;TTL>" <IP_router_inicial> '
              "<puerto_router_inicial> [archivo]")
        sys.exit(1)

    headers = sys.argv[1].split(";")
    if len(headers) != 3:
        print("Error: los headers deben tener el formato 'IP;Puerto;TTL' (ej: '127.0.0.1;8885;10')")
        sys.exit(1)

    dest_ip, dest_port, ttl = headers[0], int(headers[1]), int(headers[2])
    init_ip, init_port = sys.argv[2], int(sys.argv[3])
    file_path = sys.argv[4] if len(sys.argv) >= 5 else "archivo_prueba.txt"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            try:
                packet = create_packet({
                    "ip": dest_ip, "port": dest_port, "ttl": ttl,
                    "id": (sent + 1) % 65536, "offset": 0, "flag": 0, "message": line,
                })
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)
            sock.sendto(packet, (init_ip, init_port))
            sent += 1
    sock.close()
    print(f"{sent} paquetes de '{file_path}' enviados hacia ({dest_ip}, {dest_port}) "
          f"vía ({init_ip}, {init_port}), TTL={ttl}.")


if __name__ == "__main__":
    main()
