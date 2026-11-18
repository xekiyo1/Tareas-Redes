# Mini-Internet: Forwarding básico (con TTL)

## Archivos
- `router.py` – router (forwarding, round-robin por área, TTL). `parse_packet`, `create_packet`, `check_routes`.
- `enviar_mensaje.py` – envía un mensaje individual (Paso 5).
- `prueba_router.py` – envía un archivo línea por línea (Parte II, paso 4).
- `test_router.py` – pruebas locales (paquetes, check_routes, round-robin).
- `lanzar_red.sh` – levanta varios routers en una sola terminal.
- `rutas/` – tablas: `v1`, `v2` (+`v2_mala`), `v3` (5 routers), `ext` (R0 y R6), y `*_default` (ruta 7000 al final).

Requiere Python 3.8+.

## Header (7 bytes)
`IP(4) | puerto(2, big-endian) | TTL(1) | mensaje UTF-8`

## Uso rápido
```bash
python3 test_router.py

# 5 routers
./lanzar_red.sh v3 1 2 3 4 5
# en otra terminal:
python3 enviar_mensaje.py 127.0.0.1 8885 10 127.0.0.1 8881 "hola"
python3 prueba_router.py "127.0.0.1;8885;10" 127.0.0.1 8881 archivo_prueba.txt

# Tabla mal configurada (bucle) – sin TTL real usar TTL=255 y ver rebotes; con TTL=10 se corta
python3 router.py 127.0.0.1 8881 rutas/rutas_R1_v2.txt
python3 router.py 127.0.0.1 8882 rutas/rutas_R2_v2_mala.txt
python3 router.py 127.0.0.1 8883 rutas/rutas_R3_v2.txt
python3 enviar_mensaje.py 127.0.0.1 8883 10 127.0.0.1 8881 "hola"

# Ruta default
python3 router.py 127.0.0.1 7000 rutas/rutas_default_7000.txt &
./lanzar_red.sh v3_default 1 2 3 4 5
python3 enviar_mensaje.py 8.8.8.8 53 10 127.0.0.1 8881 "afuera"
```
