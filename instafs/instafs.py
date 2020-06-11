import argparse
import fuse, errno, os
import signal
from instafs import tree, __description__, __version__

fuse.fuse_python_api = (0, 2)


class InstaFS(fuse.Fuse):
    def __init__(self, username, *args, **kwargs):
        super(InstaFS, self).__init__(*args, **kwargs)
        self.tree = tree.Tree(username)

    def getattr(self, path):
        if path in self.tree.keys():
            return self.tree[path].get_stat()
        else:
            return -errno.ENOENT

    def readdir(self, path, offset):
        if path in self.tree:
            for r in  ['.', '..', *self.tree[path].entities]:
                yield fuse.Direntry(r)
        else:
            return -errno.ENOENT

    def open(self, path, flags):
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & os.O_RDONLY) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        if path in self.tree:
            data = self.tree[path].content
        else:
            return -errno.ENOENT

        if offset >= len(data):
            return -errno.EIO

        return data[offset:min(offset + size, len(data))]


def main():
    args_parser = argparse.ArgumentParser(description=__description__)
    args_parser.add_argument('-u', '--user', help='provide instagram username account', required=True)
    args_parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)
    args, unknown_args = args_parser.parse_known_args()

    server = InstaFS(args.user)
    server.parse(args=unknown_args, errex=1)
    old_handler = signal.signal(signal.SIGINT, signal.SIG_DFL)
    server.main()
    signal.signal(signal.SIGINT, old_handler)
