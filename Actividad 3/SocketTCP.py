import socket
import random
import time


class SocketTCP:
    """
    TCP simplificado sobre sockets UDP usando Stop & Wait.

    Formato del segmento: 2 bytes de header + payload (maximo 16 bytes).
        Byte 0: numero de secuencia (0 a 255).
        Byte 1: flags (bit 3: ACK, bit 2: SYN, bit 1: FIN).

    Se usa un unico numero de secuencia (seq_num) que representa el
    siguiente segmento a enviar o a recibir, y cada segmento de datos
    consume un numero. El ACK de un segmento lleva el mismo seq del segmento.
    """

    HEADER_SIZE = 2
    MAX_PAYLOAD = 16
    UDP_BUFFER_SIZE = HEADER_SIZE + MAX_PAYLOAD
    TIMEOUT = 2.0
    HANDSHAKE_RETRIES = 10
    DATA_RETRIES = 20
    CLOSE_RETRIES = 3
    SEQ_MOD = 256
    DEBUG = True

    def __init__(self):
        """Crea el socket UDP y el estado necesario para la conexion."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.TIMEOUT)

        self.destination_address = None
        self.seq_num = 0
        self.is_connected = False

        self.pending_recv_bytes = 0
        self.recv_buffer = b""

        self.stashed_datagram = None
        self.last_handshake_ack = None
        self.completed_syns = set()

    def _log(self, message: str):
        """Imprime un mensaje de depuracion si el modo debug esta activo."""
        if self.DEBUG:
            print(f"[DEBUG] {message}")

    @staticmethod
    def create_segment(seq: int, ack_flag: bool, syn_flag: bool, fin_flag: bool, payload: bytes = b"") -> bytes:
        """
        Crea un segmento TCP concatenando el header (2 bytes) y el payload.
        Byte 0: seq (0 a 255). Byte 1: flags (bit 3: ACK, bit 2: SYN, bit 1: FIN).
        """
        flags = 0
        if ack_flag:
            flags |= 0b1000
        if syn_flag:
            flags |= 0b0100
        if fin_flag:
            flags |= 0b0010

        if isinstance(payload, str):
            payload = payload.encode()

        return bytes([seq % SocketTCP.SEQ_MOD, flags]) + payload

    @staticmethod
    def parse_segment(segment: bytes) -> tuple:
        """
        Extrae los componentes de un segmento recibido.
        Retorna: (seq, ack_flag, syn_flag, fin_flag, payload).
        Si el segmento es mas corto que el header retorna seq=None.
        """
        if len(segment) < SocketTCP.HEADER_SIZE:
            return None, False, False, False, b""

        seq = segment[0]
        flags = segment[1]

        ack_flag = bool(flags & 0b1000)
        syn_flag = bool(flags & 0b0100)
        fin_flag = bool(flags & 0b0010)

        return seq, ack_flag, syn_flag, fin_flag, segment[2:]

    def bind(self, address: tuple):
        """Asocia el socket a una direccion local (IP, puerto)."""
        self.sock.bind(address)

    def connect(self, address: tuple):
        """
        Lado cliente (Host A) del 3-way handshake.
        Envia SYN(x), espera SYN-ACK(x+1) y responde ACK(x+2).
        Retransmite el SYN si el SYN-ACK no llega antes del timeout.
        El ultimo ACK se envia una sola vez: si se pierde, el servidor lo
        detecta en accept() (ver ahi) o lo recupera al retransmitir el SYN-ACK.
        """
        initial_seq = random.randint(0, 100)
        expected_seq = (initial_seq + 1) % self.SEQ_MOD
        syn_segment = self.create_segment(initial_seq, ack_flag=False, syn_flag=True, fin_flag=False)

        server_address = None
        attempt = 0

        while server_address is None and attempt < self.HANDSHAKE_RETRIES:
            attempt += 1
            self._log(f"Handshake: enviando SYN (seq={initial_seq}), intento {attempt}")
            self.sock.sendto(syn_segment, address)

            try:
                data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
            except socket.timeout:
                self._log(f"Handshake: timeout esperando SYN-ACK (intento {attempt})")
                continue

            seq, ack, syn, fin, _ = self.parse_segment(data)
            if ack and syn and seq == expected_seq:
                self._log(f"Handshake: SYN-ACK recibido desde {addr}")
                server_address = addr

        if server_address is None:
            raise ConnectionError("No se pudo establecer la conexion (handshake fallido).")

        self.destination_address = server_address
        self.seq_num = (initial_seq + 2) % self.SEQ_MOD
        self.last_handshake_ack = self.create_segment(self.seq_num, ack_flag=True, syn_flag=False, fin_flag=False)
        self.sock.sendto(self.last_handshake_ack, self.destination_address)

        self.is_connected = True
        self._log(f"Conectado a {self.destination_address}, seq inicial de datos={self.seq_num}")

    def _wait_syn(self) -> tuple:
        """Bloquea hasta recibir un SYN nuevo. Retorna (direccion_cliente, seq)."""
        while True:
            try:
                data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
            except socket.timeout:
                continue

            seq, ack, syn, fin, _ = self.parse_segment(data)
            if seq is None or not syn or ack:
                continue
            if (addr, seq) in self.completed_syns:
                self._log(f"Handshake: SYN duplicado de {addr} ignorado")
                continue
            return addr, seq

    def _server_handshake(self, client_address: tuple, client_seq: int):
        """
        Completa el handshake desde un socket nuevo. Retorna el socket
        conectado o None si falla.

        Caso borde (se pierde el ultimo ACK): el cliente cree estar conectado
        y envia datos. Si llega un segmento de datos con el seq esperado, se
        considera que el handshake termino y el datagrama se guarda para que
        recv() lo procese. Si no llega nada, se retransmite el SYN-ACK.
        """
        new_socket = SocketTCP()
        new_socket.bind((self.sock.getsockname()[0], 0))
        new_socket.destination_address = client_address
        new_socket.seq_num = (client_seq + 2) % self.SEQ_MOD

        syn_ack = self.create_segment((client_seq + 1) % self.SEQ_MOD, ack_flag=True, syn_flag=True, fin_flag=False)

        established = False
        attempt = 0

        while not established and attempt < self.HANDSHAKE_RETRIES:
            attempt += 1
            self._log(f"Handshake: enviando SYN-ACK a {client_address}, intento {attempt}")
            new_socket.sock.sendto(syn_ack, client_address)

            try:
                data, addr = new_socket.sock.recvfrom(self.UDP_BUFFER_SIZE)
            except socket.timeout:
                self._log(f"Handshake: timeout esperando ACK final (intento {attempt})")
                continue

            seq, ack, syn, fin, _ = self.parse_segment(data)
            if addr != client_address or seq != new_socket.seq_num or syn or fin:
                continue

            if ack:
                self._log("Handshake: ACK final recibido")
            else:
                self._log("Handshake: ACK final perdido, pero llegaron datos; handshake completo")
                new_socket.stashed_datagram = data
            established = True

        if not established:
            new_socket.sock.close()
            return None

        new_socket.is_connected = True
        self.completed_syns.add((client_address, client_seq))
        return new_socket

    def accept(self):
        """
        Lado servidor (Host B) del 3-way handshake.
        Espera un SYN, crea un nuevo socketTCP en un puerto distinto y
        completa el handshake con el. Retorna (nuevo_socket, nueva_direccion).
        """
        while True:
            client_address, client_seq = self._wait_syn()
            self._log(f"Handshake: SYN recibido desde {client_address}")

            new_socket = self._server_handshake(client_address, client_seq)
            if new_socket is not None:
                return new_socket, new_socket.sock.getsockname()
            self._log("Handshake fallido, esperando nuevas conexiones")

    def send(self, message: bytes):
        """
        Envia un mensaje con Stop & Wait.
        El primer segmento informa el largo total del mensaje y luego se envia
        el contenido en trozos de a lo mas 16 bytes.
        """
        if not self.is_connected:
            raise ConnectionError("El socket no esta conectado.")
        if isinstance(message, str):
            message = message.encode()

        self._send_stop_and_wait(str(len(message)).encode())

        for i in range(0, len(message), self.MAX_PAYLOAD):
            self._send_stop_and_wait(message[i:i + self.MAX_PAYLOAD])

    def _send_stop_and_wait(self, chunk: bytes):
        """
        Envia un segmento y retransmite cada vez que vence el timeout hasta
        recibir el ACK con el seq correspondiente. Si recibe un SYN-ACK
        retransmitido, reenvia el ultimo ACK del handshake.
        """
        segment = self.create_segment(self.seq_num, ack_flag=False, syn_flag=False, fin_flag=False, payload=chunk)

        for attempt in range(1, self.DATA_RETRIES + 1):
            self._log(f"Enviando seq={self.seq_num}, len={len(chunk)}, intento {attempt}")
            self.sock.sendto(segment, self.destination_address)

            while True:
                try:
                    data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
                except socket.timeout:
                    self._log(f"Timeout esperando ACK({self.seq_num}), retransmitiendo")
                    break

                seq, ack, syn, fin, _ = self.parse_segment(data)

                if ack and syn and self.last_handshake_ack is not None:
                    self._log("SYN-ACK retransmitido, reenviando ACK del handshake")
                    self.sock.sendto(self.last_handshake_ack, self.destination_address)
                elif ack and not syn and not fin and seq == self.seq_num:
                    self.seq_num = (self.seq_num + 1) % self.SEQ_MOD
                    return

        raise ConnectionError("La contraparte no responde (se agotaron los reintentos).")

    def recv(self, buff_size: int) -> bytes:
        """
        Recibe hasta min(message_length, buff_size) bytes del mensaje actual.

        Decisiones de diseno:
        - pending_recv_bytes guarda cuantos bytes del mensaje actual faltan
          por entregar. Si es 0, el siguiente segmento es el message_length.
        - Si al completar la lectura sobran bytes (porque un segmento de 16
          bytes sobrepasa buff_size), el sobrante queda en recv_buffer y se
          entrega al inicio de la siguiente llamada, sin perder datos.
        - Si llega un FIN se ejecuta recv_close() y se retorna b"".
        """
        if not self.is_connected:
            raise ConnectionError("El socket no esta conectado.")

        if self.pending_recv_bytes == 0:
            length_payload = self._recv_segment()
            if length_payload is None:
                return b""
            try:
                self.pending_recv_bytes = int(length_payload.decode())
            except (ValueError, UnicodeDecodeError):
                raise ValueError("Se esperaba recibir el largo del mensaje (message_length).")

        bytes_to_read = min(self.pending_recv_bytes, buff_size)

        data_buffer = bytearray(self.recv_buffer[:bytes_to_read])
        self.recv_buffer = self.recv_buffer[bytes_to_read:]

        while len(data_buffer) < bytes_to_read:
            chunk = self._recv_segment()
            if chunk is None:
                self.pending_recv_bytes = 0
                self.recv_buffer = b""
                return bytes(data_buffer)
            data_buffer.extend(chunk)

        delivered = bytes(data_buffer[:bytes_to_read])
        self.recv_buffer += bytes(data_buffer[bytes_to_read:])
        self.pending_recv_bytes -= len(delivered)

        return delivered

    def _recv_segment(self):
        """
        Espera un segmento de datos con el seq esperado y responde ACK.
        Los duplicados (seq anterior) se vuelven a confirmar sin entregarse.
        Retorna el payload, o None si se recibio un FIN (tras cerrar con
        recv_close()).
        """
        while True:
            if self.stashed_datagram is not None:
                data = self.stashed_datagram
                addr = self.destination_address
                self.stashed_datagram = None
            else:
                try:
                    data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
                except socket.timeout:
                    self._log("Recv: timeout esperando segmento, continuando")
                    continue

            seq, ack, syn, fin, payload = self.parse_segment(data)

            if seq is None or addr != self.destination_address:
                continue

            if fin and not ack:
                self._log(f"Recv: FIN recibido (seq={seq})")
                self.seq_num = (seq + 1) % self.SEQ_MOD
                self.recv_close()
                return None

            if ack or syn:
                continue

            previous_seq = (self.seq_num - 1) % self.SEQ_MOD
            if seq != self.seq_num and seq != previous_seq:
                continue

            ack_segment = self.create_segment(seq, ack_flag=True, syn_flag=False, fin_flag=False)
            self.sock.sendto(ack_segment, self.destination_address)

            if seq == self.seq_num:
                self._log(f"Recv: seq={seq}, len={len(payload)}")
                self.seq_num = (self.seq_num + 1) % self.SEQ_MOD
                return payload

            self._log(f"Recv: duplicado seq={seq}, se reenvia ACK")

    def close(self):
        """
        Cierre desde el Host A.
        Envia FIN y espera FIN+ACK hasta 3 timeouts, retransmitiendo el FIN
        en cada uno. Si llega la respuesta, envia el ultimo ACK 3 veces
        esperando un timeout entre envios. Si no llega, asume que la
        contraparte cerro. Al final libera el socket.
        """
        if not self.is_connected:
            self.sock.close()
            return

        self._log("Cierre: enviando FIN")
        fin_segment = self.create_segment(self.seq_num, ack_flag=False, syn_flag=False, fin_flag=True)

        fin_ack_received = False
        fin_ack_seq = self.seq_num
        attempt = 0

        while not fin_ack_received and attempt < self.CLOSE_RETRIES:
            attempt += 1
            self.sock.sendto(fin_segment, self.destination_address)

            try:
                while not fin_ack_received:
                    data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
                    seq, ack, syn, fin, _ = self.parse_segment(data)
                    if ack and fin:
                        fin_ack_received = True
                        fin_ack_seq = seq
            except socket.timeout:
                self._log(f"Cierre: timeout {attempt}/{self.CLOSE_RETRIES} esperando FIN+ACK")

        if fin_ack_received:
            self._log("Cierre: FIN+ACK recibido, enviando ACK final 3 veces")
            last_ack = self.create_segment((fin_ack_seq + 1) % self.SEQ_MOD, ack_flag=True, syn_flag=False, fin_flag=False)
            for i in range(3):
                self.sock.sendto(last_ack, self.destination_address)
                if i < 2:
                    time.sleep(self.TIMEOUT)
        else:
            self._log("Cierre: sin respuesta, se asume la contraparte cerrada")

        self.is_connected = False
        self.sock.close()
        self._log("Cierre: socket cerrado (Host A)")

    def recv_close(self):
        """
        Cierre desde el Host B, invocada cuando recv recibe un FIN.
        Responde FIN+ACK y espera el ACK final hasta 3 timeouts,
        reenviando el FIN+ACK en cada timeout o si llega un FIN repetido.
        Luego asume la contraparte cerrada y libera el socket.
        """
        self._log("Cierre: enviando FIN+ACK")
        fin_ack_segment = self.create_segment(self.seq_num, ack_flag=True, syn_flag=False, fin_flag=True)
        self.sock.sendto(fin_ack_segment, self.destination_address)

        timeouts = 0
        while timeouts < self.CLOSE_RETRIES:
            try:
                data, addr = self.sock.recvfrom(self.UDP_BUFFER_SIZE)
            except socket.timeout:
                timeouts += 1
                self._log(f"Cierre: timeout {timeouts}/{self.CLOSE_RETRIES} esperando ACK final")
                if timeouts < self.CLOSE_RETRIES:
                    self.sock.sendto(fin_ack_segment, self.destination_address)
                continue

            seq, ack, syn, fin, _ = self.parse_segment(data)
            if ack and not fin:
                self._log("Cierre: ACK final recibido")
                break
            if fin and not ack:
                self.sock.sendto(fin_ack_segment, self.destination_address)

        self.is_connected = False
        self.sock.close()
        self._log("Cierre: socket cerrado (Host B)")