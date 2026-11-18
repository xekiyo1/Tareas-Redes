"""Envía un mensaje individual a través del mini-Internet.

Uso:
    python3 enviar_mensaje.py <IP_final> <Puerto_final> <TTL> <IP_envio> <Puerto_envio> <Mensaje>

Ejemplo (mensaje de R1 hacia R3, entrando por R1):
    python3 enviar_mensaje.py 127.0.0.1 8883 10 127.0.0.1 8881 "hola"
"""

import socket
import sys

from router import create_packet


def main():
    if len(sys.argv) != 7:
        print(
            "Uso: python3 enviar_mensaje.py <IP_final> <Puerto_final> <TTL> "
            "<IP_envio> <Puerto_envio> <Mensaje>"
        )
        sys.exit(1)

    dest_ip = sys.argv[1]
    dest_port = int(sys.argv[2])
    ttl = int(sys.argv[3])
    send_ip = sys.argv[4]
    send_port = int(sys.argv[5])
    message = sys.argv[6]

    try:
        packet_bytes = create_packet(
            {"ip": dest_ip, "port": dest_port, "ttl": ttl, "message": message}
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(packet_bytes, (send_ip, send_port))
    sock.close()
    print(
        f"Paquete enviado a ({send_ip}, {send_port}) -> "
        f"destino final ({dest_ip}, {dest_port}), TTL={ttl}"
    )


if __name__ == "__main__":
    main()
