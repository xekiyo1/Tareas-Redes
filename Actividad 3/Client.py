import SocketTCP

address = ("localhost", 8000)

client_socketTCP = SocketTCP.SocketTCP()
client_socketTCP.connect(address)

message = "Mensaje de len=16".encode()
client_socketTCP.send(message)

message = "Mensaje de largo 19".encode()
client_socketTCP.send(message)

message = "Mensaje de largo 19".encode()
client_socketTCP.send(message)

client_socketTCP.close()