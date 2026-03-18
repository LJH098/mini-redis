class RespProtocolError(ValueError):
    pass


class RespParser:
    def parse(self, payload: bytes) -> list[str]:
        if not payload.startswith(b"*"):
            raise RespProtocolError("expected array")

        line_end = payload.find(b"\r\n")
        if line_end == -1:
            raise RespProtocolError("malformed array header")

        count = int(payload[1:line_end])
        cursor = line_end + 2
        result: list[str] = []

        for _ in range(count):
            if cursor >= len(payload) or payload[cursor:cursor + 1] != b"$":
                raise RespProtocolError("expected bulk string")

            size_end = payload.find(b"\r\n", cursor)
            if size_end == -1:
                raise RespProtocolError("malformed bulk string header")

            size = int(payload[cursor + 1:size_end])
            cursor = size_end + 2
            chunk = payload[cursor:cursor + size]
            if len(chunk) != size:
                raise RespProtocolError("incomplete bulk string")
            result.append(chunk.decode())
            cursor += size
            if payload[cursor:cursor + 2] != b"\r\n":
                raise RespProtocolError("missing bulk string terminator")
            cursor += 2

        return result
