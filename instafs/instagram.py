'''Implements instagram API'''

import requests, re, json
import urllib.parse
from collections import namedtuple
import datetime


def toutf8(data):
    if not data.endswith('\n'):
        data = data + '\n'

    return data.encode('utf-8')


class TokenManager(object):
    def __init__(self, username):
        self.username = username
        url = f'https://www.instagram.com/{username}'
        base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urllib.parse.urlparse(url))
        with requests.get(url, stream=True) as r:
            json_body = re.search('window._sharedData\s*=\s*({.*)(?=;</script>)', r.text)
            body = json.loads(json_body.group(1))
            self.user = body['entry_data']['ProfilePage'][0]['graphql']['user']
            self.id = self.user['id']

            script0 = re.search('href="([^"]+ProfilePageContainer.js[^"]+)', r.text)
            script1 = re.search('href="([^"]+Consumer.js[^"]+)', r.text)
            for script in script0, script1:
                with requests.get(base_url + script.group(1), stream=True) as r2:
                    result = re.search('s\.pagination\},queryId:"([^"]+)', r2.text)
                    if result is None:
                        continue

                    self.profile = result.group(1)

            with requests.get(base_url + script1.group(1), stream=True) as r2:
                regex = 'threadedComments\.parentByPostId\.get\(n\)\.pagination\},queryId:"([^"]+)'
                self.comment = re.search(regex, r2.text).group(1)


class Continuation(object):
    def __init__(self, query_hash, id_dict, cursor, count=12):
        variables = json.dumps({**id_dict, 'first': count, 'after': cursor})
        base_url = 'https://www.instagram.com/graphql/query'
        self.url_ = f'{base_url}/?query_hash={query_hash}&variables={urllib.parse.quote(variables)}'

    def get(self):
        return requests.get(self.url_).json()


class DataObject(object):
    def __init__(self, url=None, content=None):
        self.url_ = url
        self.content_ = content

    def __getitem__(self, idx):
        if self.content_ is None:
            with requests.get(self.url_, stream=True) as r:
                self.content_ = r.raw.read()

        return self.content_[idx]

    def __len__(self):
        if self.content_ is None:
            with requests.head(self.url_, timeout=30) as r:
                return int(r.headers['Content-Length'])

        return len(self.content_)


class Comment(object):
    CommentBody = namedtuple('CommentBody', 'text user time')

    def __init__(self, cmt, shortcode, token):
        self.count = cmt['count']
        self.token = token
        self.shortcode = shortcode
        if cmt['page_info']['has_next_page']:
            end_cursor = cmt['page_info']['end_cursor']
            self.pagination = Continuation(token, {'shortcode': shortcode}, end_cursor, count=50)
        else:
            self.pagination = None

        self.list = []
        if self.has_next():
            self.list = self.get_next()

        if 'edges' in cmt:
            self.list = self.list + self._extract_comments(cmt['edges'])

    @staticmethod
    def _extract_comments(edges):
        lst = []
        for edge in edges:
            node = edge['node']
            text = node['text']
            timestamp = datetime.datetime.fromtimestamp(node['created_at'])
            user = node['owner']['username']
            lst.append(Comment.CommentBody(text, user, timestamp))

        return lst

    def has_next(self):
        return self.pagination is not None

    def get_next(self):
        data = self.pagination.get()
        cmt = data['data']['shortcode_media']['edge_media_to_parent_comment']
        if cmt['page_info']['has_next_page']:
            end_cursor = cmt['page_info']['end_cursor']
            self.pagination = Continuation(self.token, {'shortcode': self.shortcode}, end_cursor, count=50)
        else:
            self.pagination = None

        return self._extract_comments(cmt['edges'])


class Post(object):
    Media = namedtuple('Media', 'url type id content')

    def __init__(self, edge, index, token):
        node = edge['node']
        self.index = index
        self.typename = node['__typename']
        self.comments = Comment(node['edge_media_to_comment'], node['shortcode'], token)
        self.timestamp = datetime.datetime.fromtimestamp(node['taken_at_timestamp'])
        if self.typename == 'GraphSidecar':  # GraphImage | GraphSidecar | GraphVideo
            self.media = [self._get_media(edge['node']) for edge in node['edge_sidecar_to_children']['edges']]
        else:
            self.media = [self._get_media(node)]

        captions = node['edge_media_to_caption']['edges']
        if len(captions) > 0:
            self.caption = toutf8(captions[0]['node']['text'])
        else:
            self.caption = None

        keys = ['id', 'shortcode', 'location', '__typename', 'dimensions',
                'accessibility_caption', 'edge_media_preview_like', 'edge_media_to_tagged_user']
        new_dict = {k: v for k, v in node.items() if k in keys}
        self.info = toutf8(json.dumps({**new_dict, 'url': f"https://www.instagram.com/p/{node['shortcode']}"}, indent=2))

    @staticmethod
    def _get_media(node):
        url = node['video_url'] if node['is_video'] else node['display_url']
        return Post.Media(url, node['__typename'], node['id'], DataObject(url))


class Profile(object):
    def __init__(self, username):
        self.token = TokenManager(username)
        self.userinfo = toutf8(json.dumps(self.token.user, indent=2))

        data = Continuation(self.token.profile, {'id': self.token.id}, cursor=None).get()
        media = data['data']['user']['edge_owner_to_timeline_media']

        self.count = media['count']
        self.pagination = self._extract_pagination(self.token, media['page_info'])
        self.posts = [Post(edge, self.count - idx, self.token.comment) for idx, edge in enumerate(media['edges'])]
        self.index = self.count - len(self.posts)
        self.biography = toutf8(self.token.user['biography'])

    @staticmethod
    def _extract_pagination(token, page_info):
        if page_info['has_next_page']:
            return Continuation(token.profile, {'id': token.id}, page_info['end_cursor'])
        else:
            return None

    def has_next(self):
        return self.pagination != None

    def get_next(self):
        data = self.pagination.get()
        media = data['data']['user']['edge_owner_to_timeline_media']
        self.pagination = self._extract_pagination(self.token, media['page_info'])
        posts = [Post(edge, self.index - idx, self.token.comment) for idx, edge in enumerate(media['edges'])]
        self.index -= len(posts)
        return posts


if __name__ == '__main__':
    p = Profile('instagram')  # id = 25025320

    print('id', p.token.id)
    print('profile hash', p.token.profile)
    print('comment hash', p.token.comment)

    print('biography:', p.biography)
    print('posts count', p.count)
    print('returned posts', len(p.posts))

    post = p.posts[1]
    print('post #0 media', post.media)
    print('post #0 content length', len(post.media[0].content))
    print('post #0 info', post.info)

    print('post #0 comments length', post.comments.count)
    print('post #0 comments', len(post.comments.list))
