import datetime
import fuse
from instafs import instagram
import stat
import os
import copy


class FileInfo(object):
    def __init__(self, is_file, time, uid, gid, content=None, entities=[]):
        self.stat_ = fuse.Stat()
        self.stat_.st_atime = self.stat_.st_mtime = self.stat_.st_ctime = time.timestamp()
        self.stat_.st_mode = stat.S_IFREG | 0o444 if is_file else stat.S_IFDIR | 0o755
        self.stat_.st_uid = uid
        self.stat_.st_gid = gid
        self.stat_.st_nlink = 1 if is_file else 2

        self.content = content
        self.entities = entities

    def get_stat(self):
        mystat = copy.copy(self.stat_)
        mystat.st_size = len(self.content) if self.content else 4096
        mystat.st_nlink += len(self.entities)

        return mystat


class LazyList(object):
    def __init__(self, callback, arg):
        self.callback = callback
        self.arg = arg
        self.entities = []

    def __getitem__(self, idx):
        if self.entities == []:
            self.entities = self.callback(self.arg)
            self.callback = None
            self.arg = None

        return self.entities[idx]

    def __len__(self):
        return len(self.entities)  # it'll be zero if no one has visited yet


class Tree(dict):
    def __init__(self, username):
        super(Tree, self).__init__()

        self.uid, self.gid = os.getuid(), os.getgid()
        self.ctime = datetime.datetime.now()
        self.extmap = {'GraphImage': 'jpg', 'GraphVideo': 'mp4'}

        self.profile = instagram.Profile(username)
        root_entities = self._add_posts('', self.profile.posts)

        self['/biography.txt'] = FileInfo(True, self.ctime, self.uid, self.gid, self.profile.biography)
        root_entities.append('biography.txt')

        self['/userinfo.json'] = FileInfo(True, self.ctime, self.uid, self.gid, self.profile.userinfo)
        root_entities.append('userinfo.json')

        self['/'] = FileInfo(False, self.ctime, self.uid, self.gid, entities=root_entities)

    def _add_posts(self, path, posts):
        entities = []
        for post in posts:
            name = str(post.index)
            lst = ['info.json']
            self[f'{path}/{name}/{lst[-1]}'] = FileInfo(True, post.timestamp, self.uid, self.gid, post.info)

            if post.caption is not None:
                lst.append('caption.txt')
                self[f'{path}/{name}/{lst[-1]}'] = FileInfo(True, post.timestamp, self.uid, self.gid, post.caption)

            for i, item in enumerate(post.media):
                ext = self.extmap[item.type]
                lst.append(f'{i}.{ext}')
                self[f'{path}/{name}/{lst[-1]}'] = FileInfo(True, post.timestamp, self.uid, self.gid, item.content)

            self[f'{path}/{name}'] = FileInfo(False, post.timestamp, self.uid, self.gid, entities=lst)
            entities.append(name)

        if self.profile.has_next():
            next_list = LazyList(self._next_posts, f'{path}/next')
            self[f'{path}/next'] = FileInfo(False, self.ctime, self.uid, self.gid, entities=next_list)
            entities.append('next')

        return entities

    def _next_posts(self, path):
        return self._add_posts(path, self.profile.load_next())
