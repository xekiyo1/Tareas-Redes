"""Envía un datagrama IP individual al mini-Internet.

Uso:
    python3 enviar_mensaje.py <IP_final> <Puerto_final> <TTL> <IP_envio> <Puerto_envio> <Mensaje>
                              [--id ID] [--offset N] [--flag {0,1}] [--total BYTES]

Opciones:
    --id      ID del datagrama (0-65535). Por defecto aleatorio (se imprime).
    --offset  Offset del mensaje (por defecto 0).
    --flag    FLAG More-Fragments (por defecto 0).
    --total   Tamaño TOTAL del paquete en bytes, header incluido. El mensaje se repite
              (y corta) hasta llenar ese tamaño. Ej: --total 150 -> mensaje de 134 bytes.

Ejemplos:
    # paquete chico de R1 a R5
    python3 enviar_mensaje.py 127.0.0.1 8885 10 127.0.0.1 8881 "hola!" --id 347
    # paquete de 150 bytes de R1 a R5
    python3 enviar_mensaje.py 127.0.0.1 8885 64 127.0.0.1 8881 "abc-" --id 1 --total 150
"""

import argparse
import random
import socket
import sys

from router import HEADER_SIZE, create_packet


def main():
    ap = argparse.ArgumentParser(description="Envía un datagrama IP al mini-Internet")
    ap.add_argument("ip_final")
    ap.add_argument("puerto_final", type=int)
    ap.add_argument("ttl", type=int)
    ap.add_argument("ip_envio")
    ap.add_argument("puerto_envio", type=int)
    ap.add_argument("mensaje")
    ap.add_argument("--id", type=int, default=None, dest="pkt_id")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--flag", type=int, default=0, choices=(0, 1))
    ap.add_argument("--total", type=int, default=None)
    args = ap.parse_args()

    message = args.mensaje.encode("utf-8")
    if args.total is not None:
        payload_len = args.total - HEADER_SIZE
        if payload_len < 0 or not message:
            print(f"Error: --total debe ser >= {HEADER_SIZE} y el mensaje no puede ser vacío")
            sys.exit(1)
        message = (message * (payload_len // len(message) + 1))[:payload_len]

    pkt_id = args.pkt_id if args.pkt_id is not None else random.randint(1, 65535)

    try:
        packet = create_packet({
            "ip": args.ip_final, "port": args.puerto_final, "ttl": args.ttl,
            "id": pkt_id, "offset": args.offset, "flag": args.flag, "message": message,
        })
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(packet, (args.ip_envio, args.puerto_envio))
    sock.close()
    print(
        f"Paquete de {len(packet)} bytes enviado a ({args.ip_envio}, {args.puerto_envio}) -> "
        f"destino final ({args.ip_final}, {args.puerto_final}), TTL={args.ttl}, "
        f"ID={pkt_id}, offset={args.offset}, flag={args.flag}, tamaño={len(message)}"
    )


if __name__ == "__main__":
    main()
