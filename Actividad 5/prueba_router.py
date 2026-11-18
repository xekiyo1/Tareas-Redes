"""Envía un archivo línea por línea a través del mini-Internet.

Uso:
    python3 prueba_router.py "<IP;Puerto;TTL>" <IP_router_inicial> <puerto_router_inicial> [archivo]

Ejemplo (de R1 hacia R5, archivo por defecto archivo_prueba.txt):
    python3 prueba_router.py "127.0.0.1;8885;10" 127.0.0.1 8881

Nota: en bash hay que poner los headers entre comillas, si no ';' se interpreta
como separador de comandos. Las líneas vacías del archivo se omiten (no generan paquete).
"""

import socket
import sys

from router import create_packet


def main():
    if len(sys.argv) < 4:
        print(
            "Uso: python3 prueba_router.py <IP;Puerto;TTL> <IP_router_inicial> "
            "<puerto_router_inicial> [archivo]"
        )
        sys.exit(1)

    headers = sys.argv[1].split(";")
    if len(headers) != 3:
        print("Error: los headers deben tener el formato 'IP;Puerto;TTL' (ej: '127.0.0.1;8885;10')")
        sys.exit(1)

    dest_ip = headers[0]
    dest_port = int(headers[1])
    ttl = int(headers[2])
    init_ip = sys.argv[2]
    init_port = int(sys.argv[3])
    file_path = sys.argv[4] if len(sys.argv) >= 5 else "archivo_prueba.txt"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.rstrip("\r\n")
            if not clean_line:
                continue
            try:
                packet_bytes = create_packet(
                    {"ip": dest_ip, "port": dest_port, "ttl": ttl, "message": clean_line}
                )
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)
            sock.sendto(packet_bytes, (init_ip, init_port))
            sent += 1

    sock.close()
    print(
        f"{sent} paquetes de '{file_path}' enviados hacia ({dest_ip}, {dest_port}) "
        f"vía ({init_ip}, {init_port}), TTL={ttl}."
    )


if __name__ == "__main__":
    main()
