"""Router del mini-Internet (Forwarding básico con round-robin y TTL).

Uso:
    python3 router.py <router_IP> <router_puerto> <router_rutas.txt>

Formato del paquete (bytes):
    0..3  : IPv4 destino (1 byte por octeto)
    4..5  : puerto destino (big-endian)
    6     : TTL (1 byte)
    7..N  : mensaje (UTF-8)

Formato de cada línea de la tabla de rutas:
    Red_CIDR Puerto_Ini Puerto_Fin NextHop_IP NextHop_Puerto
"""

import ipaddress
import socket
import sys
from typing import Optional, Tuple

HEADER_SIZE = 7

# Estado de Round-Robin por "área de red":
#   (cidr, puerto_inicial, puerto_final) -> índice de la próxima ruta a usar
rr_state = {}


# ---------------------------------------------------------------------------
# Paquetes
# ---------------------------------------------------------------------------
def parse_packet(ip_packet: bytes) -> dict:
    """Extrae IP, puerto, TTL y mensaje desde un paquete en bytes."""
    if len(ip_packet) < HEADER_SIZE:
        raise ValueError(
            f"Paquete IP inválido: largo {len(ip_packet)} < {HEADER_SIZE} bytes."
        )

    ip_str = ".".join(str(b) for b in ip_packet[0:4])
    port = int.from_bytes(ip_packet[4:6], byteorder="big")
    ttl = ip_packet[6]
    message = ip_packet[7:].decode("utf-8", errors="replace")

    return {"ip": ip_str, "port": port, "ttl": ttl, "message": message}


def create_packet(parsed_ip_packet: dict) -> bytes:
    """Construye un paquete en bytes desde el diccionario de parse_packet."""
    ip_bytes = ipaddress.IPv4Address(parsed_ip_packet["ip"]).packed

    port = int(parsed_ip_packet["port"])
    if not 0 <= port <= 65535:
        raise ValueError(f"Puerto fuera de rango (0-65535): {port}")

    ttl = int(parsed_ip_packet["ttl"])
    if not 0 <= ttl <= 255:
        raise ValueError(f"TTL fuera de rango (0-255): {ttl}")

    msg_bytes = parsed_ip_packet["message"].encode("utf-8")
    return ip_bytes + port.to_bytes(2, "big") + ttl.to_bytes(1, "big") + msg_bytes


# ---------------------------------------------------------------------------
# Tabla de rutas
# ---------------------------------------------------------------------------
def ip_in_network(ip_str: str, cidr_str: str) -> bool:
    """True si la IPv4 pertenece a la subred CIDR."""
    return ipaddress.ip_address(ip_str) in ipaddress.ip_network(cidr_str, strict=False)


def check_routes(
    routes_file_name: str, destination_address: Tuple[str, int]
) -> Optional[Tuple[str, int]]:
    """Retorna el next hop (ip, puerto) para destination_address, o None.

    Recorre la tabla en orden. La primera ruta que calza define el "área de red"
    (cidr, p_ini, p_fin). Entre todas las rutas de esa misma área se elige el
    next hop con round-robin, llevando un contador independiente por área.
    """
    dest_ip, dest_port = destination_address
    matching_routes = []

    with open(routes_file_name, "r", encoding="utf-8") as f:
        for n_line, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            try:
                cidr = parts[0]
                p_start = int(parts[1])
                p_end = int(parts[2])
                nh_ip = parts[3]
                nh_port = int(parts[4])
                matches = ip_in_network(dest_ip, cidr) and p_start <= dest_port <= p_end
            except (IndexError, ValueError):
                print(f"[Aviso] Línea {n_line} mal formada en {routes_file_name}: {line!r}")
                continue

            if matches:
                matching_routes.append(((cidr, p_start, p_end), (nh_ip, nh_port)))

    if not matching_routes:
        return None

    first_area = matching_routes[0][0]
    candidates = [nh for area, nh in matching_routes if area == first_area]

    idx = rr_state.get(first_area, 0) % len(candidates)
    rr_state[first_area] = (idx + 1) % len(candidates)
    return candidates[idx]


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 4:
        print("Uso: python3 router.py <router_IP> <router_puerto> <router_rutas.txt>")
        sys.exit(1)

    router_ip = sys.argv[1]
    router_port = int(sys.argv[2])
    routes_file = sys.argv[3]
    my_address = (router_ip, router_port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(my_address)
    print(f"[Router {router_ip}:{router_port}] Escuchando paquetes...")

    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)  # bloqueante
            except ConnectionResetError:
                # Windows: ICMP "port unreachable" de un envío anterior.
                continue

            try:
                packet = parse_packet(data)
            except ValueError as e:
                print(f"[Error] {e}")
                continue

            dest_address = (packet["ip"], packet["port"])

            # 1. Procesar solo si TTL > 0 (también aplica si el destino es este router)
            if packet["ttl"] <= 0:
                print(f"Se recibió paquete {data} con TTL 0")
                continue

            # 2. ¿Es para este router?
            if dest_address == my_address:
                print(packet["message"])
                continue

            # 3. Forwarding
            next_hop = check_routes(routes_file, dest_address)
            if next_hop is None:
                print(f"No hay rutas hacia {dest_address} para paquete {data}")
                continue

            packet["ttl"] -= 1
            forwarded = create_packet(packet)
            print(
                f"redirigiendo paquete {data} con destino final {dest_address} "
                f"desde {my_address} hacia {next_hop}"
            )
            sock.sendto(forwarded, next_hop)
    except KeyboardInterrupt:
        print(f"\n[Router {router_ip}:{router_port}] Detenido.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
