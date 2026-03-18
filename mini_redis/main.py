from mini_redis.config import ServerConfig
from mini_redis.core.dispatcher import CommandDispatcher, default_handlers
from mini_redis.core.storage import Storage
from mini_redis.expiration.manager import get_expiration_manager
from mini_redis.server.tcp_server import TcpServer


def create_app() -> TcpServer:
    config = ServerConfig()
    storage = Storage()
    storage.set_expiration_checker(get_expiration_manager().is_expired)
    dispatcher = CommandDispatcher(storage=storage)
    dispatcher.register_many(default_handlers())
    return TcpServer(host=config.host, port=config.port, dispatcher=dispatcher)


def main() -> None:
    server = create_app()
    server.serve_forever()


if __name__ == "__main__":
    main()
