# Mini-Internet: Fragmentación (sobre Forwarding básico con TTL)

Python 3.8+. Sin dependencias externas.

## Archivos
| Archivo | Para qué |
|---|---|
| `router.py` | Router: `parse_packet`, `create_packet`, `check_routes` (→ `(next_hop, MTU)`), `fragment_IP_packet`, `reassemble_IP_packet`, buffer por ID |
| `enviar_mensaje.py` | Envía un datagrama (`--id`, `--offset`, `--flag`, `--total`) |
| `prueba_router.py` | Envía un archivo línea por línea (ID distinto por línea) |
| `prueba_fragmentos.py` | Envía a mano los fragmentos de 2 IDs: orden / desorden / intercalado / mezcla |
| `test_fragmentacion.py` | 15 pruebas unitarias (sin sockets) |
| `test_integracion.py` | Levanta los 5 routers y prueba todo con UDP real |
| `lanzar_red.sh` | Levanta varios routers en una terminal |
| `rutas/` | `rutas_R1..R5_v3_mtu.txt` (las del enunciado) |

## Header (16 bytes, big-endian)
`IP(4) | Puerto(2) | TTL(1) | ID(2) | Offset(2) | Tamaño(4) | FLAG(1) | mensaje`

## Decisiones de diseño
- **El mensaje es `bytes`** en todo el camino y se decodifica a UTF-8 solo al imprimir, ya reensamblado
  (al fragmentar se puede cortar en medio de un carácter multibyte).
- **Tamaño** = bytes del mensaje de *ese* paquete/fragmento; `parse_packet` rechaza paquetes donde no coincide.
- **Fragmentación:** si `len(paquete) <= MTU` devuelve `[paquete]`; si no, trozos de `MTU - 16` bytes.
  Offset = offset original + desplazamiento (sirve para re-fragmentar). El último sub-fragmento hereda el FLAG original.
- **TTL:** se descarta si TTL = 0 al recibir (incluso si el destino es el router); se decrementa **una vez** antes de fragmentar.
- **Round-robin:** una decisión por paquete/fragmento recibido, por área `(cidr, p_ini, p_fin)`. Todos los fragmentos
  que salen de una misma fragmentación van por el mismo enlace; cada fragmento se vuelve a rutear en el router siguiente.
- **Reensamblaje:** ordena por offset, exige cobertura continua desde 0 y que el último trozo tenga FLAG=0. Tolera duplicados.
- **`check_routes`** retorna `(None, None)` si no hay ruta (así siempre se puede desempaquetar). Si la línea no trae MTU se usa 65535.

## Uso
```bash
python3 test_fragmentacion.py
python3 test_integracion.py

bash lanzar_red.sh v3_mtu 1 2 3 4 5
# en otra terminal:
python3 enviar_mensaje.py 127.0.0.1 8885 10 127.0.0.1 8881 "hola!" --id 347
python3 enviar_mensaje.py 127.0.0.1 8885 64 127.0.0.1 8881 "abc-" --id 1 --total 150     # 150 bytes
python3 enviar_mensaje.py 127.0.0.1 8881 64 127.0.0.1 8885 "xyz-" --id 2 --total 150     # entrando por R5
python3 prueba_fragmentos.py 127.0.0.1 8885 127.0.0.1 8885 50 intercalado
```
Para paquetes de 150 bytes usa TTL alto (≈64): con round-robin pueden dar varias vueltas R2↔R3/R4 y un TTL=10 podría matar fragmentos.

## Limitaciones conocidas
- El buffer de reensamblaje no tiene timeout: un datagrama incompleto queda guardado.
- El buffer se indexa solo por ID (como pide el enunciado): dos orígenes con el mismo ID colisionarían.
