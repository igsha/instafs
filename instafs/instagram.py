'''Implements instagram API'''

import requests
import re, json, sys
import urllib.parse
from collections import namedtuple
import datetime
from requests.adapters import HTTPAdapter


default_headers = {'User-agent': 'My user agent 1.0'}

def toutf8(data):
    if not data.endswith('\n'):
        data = data + '\n'

    return data.encode('utf-8')


class TokenManager(object):
    def __init__(self, username):
        self.username = username
        url = f'https://www.instagram.com/{username}'
        base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urllib.parse.urlparse(url))
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=5))
        with self.session.get(url, stream=False, allow_redirects=True, headers=default_headers) as r:
            json_body = re.search('window._sharedData\s*=\s*({.*)(?=;</script>)', r.text)
            body = json.loads(json_body.group(1))
            self.user = body['entry_data']['ProfilePage'][0]['graphql']['user']
            self.id = self.user['id']

            self.profile = None
            self.comment = None

            script0 = re.search('href="([^"]+ProfilePageContainer.js[^"]+)', r.text)
            script1 = re.search('href="([^"]+ConsumerLibCommons.js[^"]+)', r.text)
            script2 = re.search('href="([^"]+Consumer.js[^"]+)', r.text)
            for script in script0, script1, script2:
                with self.session.get(base_url + script.group(1), stream=True, allow_redirects=True, headers=default_headers) as r2:
                    result = re.search('\w\.pagination\},queryId:"([^"]+)', r2.text)
                    if result and not self.profile:
                        self.profile = result.group(1)

                    result = re.search('threadedComments\.parentByPostId\.get\(\w\)\.pagination\}?,queryId:"([^"]+)', r2.text)
                    if result and not self.comment:
                        self.comment = result.group(1)


class Continuation(object):
    def __init__(self, session, query_hash, id_dict, cursor, count=12):
        variables = json.dumps({**id_dict, 'first': count, 'after': cursor})
        base_url = 'https://www.instagram.com/graphql/query'
        self.url_ = f'{base_url}/?query_hash={query_hash}&variables={urllib.parse.quote(variables)}'
        self.session = session

    def get(self):
        try:
            return self.session.get(self.url_, headers=default_headers).json()
        except Exception as e:
            print("Got " + str(e), file=sys.stderr)
            raise


class DataObject(object):
    def __init__(self, session, url=None, content=None):
        self.url_ = url
        self.content_ = content
        self.session = session

    def __getitem__(self, idx):
        if self.content_ is None:
            with self.session.get(self.url_, stream=True, headers=default_headers) as r:
                self.content_ = r.raw.read()

        return self.content_[idx]

    def __len__(self):
        if self.content_ is None:
            with self.session.head(self.url_, timeout=30, headers=default_headers) as r:
                return int(r.headers['Content-Length'])

        return len(self.content_)


class Comment(object):
    CommentBody = namedtuple('CommentBody', 'text user time')

    def __init__(self, session, cmt, shortcode, token):
        self.count = cmt['count']
        self.token = token
        self.shortcode = shortcode
        if cmt['page_info']['has_next_page']:
            end_cursor = cmt['page_info']['end_cursor']
            self.pagination = Continuation(session, token, {'shortcode': shortcode}, end_cursor, count=50)
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
        try:
            data = self.pagination.get()
            cmt = data['data']['shortcode_media']['edge_media_to_parent_comment']
            if cmt['page_info']['has_next_page']:
                end_cursor = cmt['page_info']['end_cursor']
                self.pagination = Continuation(self.pagination.session, self.token, {'shortcode': self.shortcode}, end_cursor, count=50)
            else:
                self.pagination = None

            return self._extract_comments(cmt['edges'])
        except Exception as e:
            print('Broken pagination: ' + str(e), file=sys.stderr)
            return []


class Post(object):
    Media = namedtuple('Media', 'url type id content')

    def __init__(self, session, edge, index, token):
        node = edge['node']
        self.index = index
        self.typename = node['__typename']
        self.comments = Comment(session, node['edge_media_to_comment'], node['shortcode'], token)
        self.timestamp = datetime.datetime.fromtimestamp(node['taken_at_timestamp'])
        if self.typename == 'GraphSidecar':  # GraphImage | GraphSidecar | GraphVideo
            self.media = [self._get_media(session, edge['node']) for edge in node['edge_sidecar_to_children']['edges']]
        else:
            self.media = [self._get_media(session, node)]

        captions = node['edge_media_to_caption']['edges']
        if len(captions) > 0:
            self.caption = toutf8(captions[0]['node']['text'])
        else:
            self.caption = None

        self.info = toutf8(json.dumps(node, indent=2))

    @staticmethod
    def _get_media(session, node):
        url = node['video_url'] if node['is_video'] else node['display_url']
        return Post.Media(url, node['__typename'], node['id'], DataObject(session, url))


class Profile(object):
    def __init__(self, username):
        self.token = TokenManager(username)
        self.userinfo = toutf8(json.dumps(self.token.user, indent=2))

        data = Continuation(self.token.session, self.token.profile, {'id': self.token.id}, cursor=None).get()
        media = data['data']['user']['edge_owner_to_timeline_media']

        self.count = media['count']
        self.pagination = self._extract_pagination(self.token, media['page_info'])
        self.posts = [Post(self.token.session, edge, self.count - idx, self.token.comment) for idx, edge in enumerate(media['edges'])]
        self.index = self.count - len(self.posts)
        self.biography = toutf8(self.token.user['biography'])

    @staticmethod
    def _extract_pagination(token, page_info):
        if page_info['has_next_page']:
            return Continuation(token.session, token.profile, {'id': token.id}, page_info['end_cursor'])
        else:
            return None

    def has_next(self):
        return self.pagination != None

    def get_next(self):
        data = self.pagination.get()
        media = data['data']['user']['edge_owner_to_timeline_media']
        self.pagination = self._extract_pagination(self.token, media['page_info'])
        posts = [Post(self.token.session, edge, self.index - idx, self.token.comment) for idx, edge in enumerate(media['edges'])]
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
    print('post #0 info length', len(post.info))

    print('post #0 comments length', post.comments.count)
    print('post #0 comments', len(post.comments.list))
