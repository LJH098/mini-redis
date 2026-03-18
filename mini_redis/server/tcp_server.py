class TcpServer:
    def __init__(self, host: str, port: int, dispatcher) -> None:
        self.host = host
        self.port = port
        self.dispatcher = dispatcher

    def serve_forever(self) -> None:
        raise NotImplementedError("TCP server is owned by role 1")
