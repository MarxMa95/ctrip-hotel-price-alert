from http.server import ThreadingHTTPServer

from .api import AppHandler
from .config import APP_PORT
from .repository import init_db
from .services.checker import Poller, check_watcher


def main() -> None:
    init_db()
    poller = Poller()
    poller.start()
    server = ThreadingHTTPServer(('127.0.0.1', APP_PORT), AppHandler)
    print(f'Hotel price alert running at http://127.0.0.1:{APP_PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
        server.server_close()


__all__ = ['AppHandler', 'Poller', 'check_watcher', 'main']
