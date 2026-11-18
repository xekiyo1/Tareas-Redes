"""Router del mini-Internet con TTL, MTU, fragmentación y reensamblaje.

Uso:
    python3 router.py <router_IP> <router_puerto> <router_rutas.txt>

Header (16 bytes, big-endian):
    bytes 0..3    IPv4 destino (1 byte por octeto)
    bytes 4..5    puerto destino
    byte  6       TTL
    bytes 7..8    ID (identifica a todos los fragmentos de un mismo datagrama)
    bytes 9..10   Offset (en bytes, relativo al mensaje del datagrama original)
    bytes 11..14  Tamaño del mensaje de ESTE paquete/fragmento (sin header)
    byte  15      FLAG (1 = vienen más fragmentos, 0 = último fragmento o paquete completo)
    bytes 16..N   mensaje (bytes; se decodifica como UTF-8 solo al imprimir)

Formato de cada línea de la tabla de rutas:
    Red_CIDR Puerto_Ini Puerto_Fin NextHop_IP NextHop_Puerto [MTU]
Si falta el MTU se asume DEFAULT_MTU (sin fragmentación en la práctica).
"""

import ipaddress
import socket
import struct
import sys
from typing import Dict, List, Optional, Tuple

HEADER_STRUCT = struct.Struct(">4sHBHHIB")  # 4+2+1+2+2+4+1 = 16 bytes, sin padding
HEADER_SIZE = HEADER_STRUCT.size
DEFAULT_MTU = 65535

# Round-robin: (cidr, puerto_ini, puerto_fin) -> índice de la próxima ruta del área
rr_state: Dict[tuple, int] = {}

# Fragmentos recibidos para este router: ID -> lista de paquetes/fragmentos (bytes crudos)
fragment_buffer: Dict[int, List[bytes]] = {}


# ---------------------------------------------------------------------------
# Paquetes
# ---------------------------------------------------------------------------
def _check_range(name: str, value: int, lo: int, hi: int) -> int:
    value = int(value)
    if not lo <= value <= hi:
        raise ValueError(f"{name} fuera de rango ({lo}-{hi}): {value}")
    return value


def parse_packet(ip_packet: bytes) -> dict:
    """Bytes -> dict con ip, port, ttl, id, offset, size, flag y message (bytes)."""
    if len(ip_packet) < HEADER_SIZE:
        raise ValueError(
            f"Paquete IP inválido: largo {len(ip_packet)} < header de {HEADER_SIZE} bytes."
        )
    ip_raw, port, ttl, pkt_id, offset, size, flag = HEADER_STRUCT.unpack_from(ip_packet)
    message = ip_packet[HEADER_SIZE:]

    if size != len(message):
        raise ValueError(
            f"Paquete inconsistente: Tamaño={size} pero el mensaje mide {len(message)} bytes."
        )
    if flag not in (0, 1):
        raise ValueError(f"FLAG inválido: {flag}")

    return {
        "ip": str(ipaddress.IPv4Address(ip_raw)),
        "port": port,
        "ttl": ttl,
        "id": pkt_id,
        "offset": offset,
        "size": size,
        "flag": flag,
        "message": message,
    }


def create_packet(parsed_ip_packet: dict) -> bytes:
    """dict (como el de parse_packet) -> bytes. 'size' se recalcula desde el mensaje.

    'message' puede ser bytes o str (si es str se codifica en UTF-8).
    """
    p = parsed_ip_packet
    message = p["message"]
    if isinstance(message, str):
        message = message.encode("utf-8")

    return HEADER_STRUCT.pack(
        ipaddress.IPv4Address(p["ip"]).packed,
        _check_range("Puerto", p["port"], 0, 65535),
        _check_range("TTL", p["ttl"], 0, 255),
        _check_range("ID", p["id"], 0, 65535),
        _check_range("Offset", p["offset"], 0, 65535),
        len(message),
        _check_range("FLAG", p["flag"], 0, 1),
    ) + bytes(message)


# ---------------------------------------------------------------------------
# Fragmentación y reensamblaje
# ---------------------------------------------------------------------------
def fragment_IP_packet(IP_packet: bytes, MTU: int) -> List[bytes]:
    """Fragmenta IP_packet para que cada trozo (header incluido) mida <= MTU.

    - Si cabe, retorna [IP_packet].
    - Sirve también para re-fragmentar un fragmento: el offset parte desde el
      offset que ya traía y el último sub-fragmento hereda el FLAG original
      (si el fragmento tenía FLAG=1 todavía faltan trozos del datagrama).
    """
    if len(IP_packet) <= MTU:
        return [IP_packet]

    max_payload = MTU - HEADER_SIZE
    if max_payload <= 0:
        raise ValueError(f"MTU={MTU} no alcanza ni para el header ({HEADER_SIZE} bytes)")

    pkt = parse_packet(IP_packet)
    data = pkt["message"]
    fragments = []
    for start in range(0, len(data), max_payload):
        is_last = start + max_payload >= len(data)
        fragments.append(
            create_packet(
                {
                    **pkt,
                    "message": data[start:start + max_payload],
                    "offset": pkt["offset"] + start,
                    "flag": pkt["flag"] if is_last else 1,
                }
            )
        )
    return fragments


def reassemble_IP_packet(fragment_list: List[bytes]) -> Optional[bytes]:
    """Reensambla un datagrama desde sus fragmentos (en cualquier orden).

    Retorna el paquete completo (offset=0, FLAG=0, Tamaño total) o None si la lista
    está incompleta: falta el inicio, falta un trozo intermedio o falta el final
    (el último trozo contiguo todavía tiene FLAG=1). Tolera duplicados.
    Un paquete sin fragmentar (offset=0, FLAG=0) se reensambla a sí mismo.
    """
    parsed = []
    for raw in fragment_list:
        try:
            parsed.append(parse_packet(raw))
        except ValueError:
            continue
    if not parsed:
        return None

    parsed.sort(key=lambda p: p["offset"])

    expected = 0          # próximo byte del mensaje original que necesitamos
    last_flag = None      # FLAG del último fragmento que extendió la cobertura
    chunks = []
    for p in parsed:
        start = p["offset"]
        end = start + len(p["message"])
        if last_flag is not None and end <= expected:
            continue                       # duplicado (o totalmente cubierto)
        if start > expected:
            return None                    # falta un trozo (inicio o intermedio)
        chunks.append(p["message"][expected - start:])
        expected = end
        last_flag = p["flag"]

    if last_flag != 0:
        return None                        # faltan fragmentos al final

    return create_packet({**parsed[0], "offset": 0, "flag": 0, "message": b"".join(chunks)})


def store_and_reassemble(
    buffers: Dict[int, List[bytes]], data: bytes, pkt_id: int
) -> Optional[bytes]:
    """Guarda `data` bajo su ID e intenta reensamblar. Si lo logra, limpia ese ID."""
    frags = buffers.setdefault(pkt_id, [])
    if data not in frags:                  # ignora duplicados exactos
        frags.append(data)
    complete = reassemble_IP_packet(frags)
    if complete is not None:
        del buffers[pkt_id]
    return complete


# ---------------------------------------------------------------------------
# Tabla de rutas
# ---------------------------------------------------------------------------
def ip_in_network(ip_str: str, cidr_str: str) -> bool:
    return ipaddress.ip_address(ip_str) in ipaddress.ip_network(cidr_str, strict=False)


def check_routes(
    routes_file_name: str, destination_address: Tuple[str, int]
) -> Tuple[Optional[Tuple[str, int]], Optional[int]]:
    """Retorna (next_hop_address, MTU) o (None, None) si no hay ruta.

    Round-robin independiente por área (cidr, puerto_ini, puerto_fin): la primera
    ruta que calza define el área y se rota entre todas las rutas de esa área.
    """
    dest_ip, dest_port = destination_address
    matching = []

    with open(routes_file_name, "r", encoding="utf-8") as f:
        for n_line, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            try:
                cidr = parts[0]
                p_start, p_end = int(parts[1]), int(parts[2])
                nh = (parts[3], int(parts[4]))
                mtu = int(parts[5]) if len(parts) > 5 else DEFAULT_MTU
                hit = ip_in_network(dest_ip, cidr) and p_start <= dest_port <= p_end
            except (IndexError, ValueError):
                print(f"[Aviso] Línea {n_line} mal formada en {routes_file_name}: {line!r}")
                continue
            if hit:
                matching.append(((cidr, p_start, p_end), nh, mtu))

    if not matching:
        return None, None

    area = matching[0][0]
    candidates = [(nh, mtu) for a, nh, mtu in matching if a == area]
    idx = rr_state.get(area, 0) % len(candidates)
    rr_state[area] = (idx + 1) % len(candidates)
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
                data, _ = sock.recvfrom(4096)
            except ConnectionResetError:     # Windows: ICMP de un envío anterior
                continue

            try:
                packet = parse_packet(data)
            except ValueError as e:
                print(f"[Error] {e}")
                continue

            dest_address = (packet["ip"], packet["port"])

            # 1. Procesar solo si TTL > 0 (vale para paquetes y fragmentos)
            if packet["ttl"] <= 0:
                print(f"Se recibió paquete {data} con TTL 0")
                continue

            # 2. Paquete/fragmento para este router: guardar e intentar reensamblar
            if dest_address == my_address:
                complete = store_and_reassemble(fragment_buffer, data, packet["id"])
                if complete is None:
                    print(
                        f"[debug] fragmento recibido id={packet['id']} "
                        f"offset={packet['offset']} flag={packet['flag']}: faltan fragmentos"
                    )
                else:
                    print(parse_packet(complete)["message"].decode("utf-8", errors="replace"))
                continue

            # 3. Forwarding
            next_hop, mtu = check_routes(routes_file, dest_address)
            if next_hop is None:
                print(f"No hay rutas hacia {dest_address} para paquete {data}")
                continue

            packet["ttl"] -= 1                       # una sola vez, antes de fragmentar
            forwarded = create_packet(packet)
            try:
                fragments = fragment_IP_packet(forwarded, mtu)
            except ValueError as e:
                print(f"[Error] no se puede fragmentar para MTU={mtu}: {e}")
                continue

            if len(fragments) > 1:
                print(
                    f"[debug] fragmentando id={packet['id']} offset={packet['offset']} "
                    f"({len(forwarded)} bytes) con MTU={mtu} en {len(fragments)} fragmentos"
                )
            for frag in fragments:
                print(
                    f"redirigiendo paquete {frag} con destino final {dest_address} "
                    f"desde {my_address} hacia {next_hop}"
                )
                sock.sendto(frag, next_hop)
    except KeyboardInterrupt:
        print(f"\n[Router {router_ip}:{router_port}] Detenido.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
