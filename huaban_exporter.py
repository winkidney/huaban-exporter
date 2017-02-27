#!/usr/bin/env python

import json
import logging
import os
import Queue
import random
import string
from functools import wraps
from threading import Thread
from time import sleep

import requests
from pprint import pprint
from urlparse import urljoin

import cmdtree as cmd
from tqdm import tqdm

_DEBUG = False


IMAGE_URL_TPL = "http://img.hb.aicdn.com/{file_key}"
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; WOW64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/56.0.2924.87 Safari/537.36",
}


def _random_string(length):
    return ''.join(
        random.choice(string.ascii_lowercase + string.digits)
        for _ in range(length)
    )


def _safe_file_name(file_name):
    return file_name.replace("/", "_")


def _get_file_ext(mime_type):
    return mime_type.split("/")[-1]


def get_pins(board_dict):
    board = board_dict
    pins = []
    for info in board['pins']:
        ext = _get_file_ext(info['file']['type'])
        file_name = "%s.%s" % (info['pin_id'], ext)
        meta = {
            "pin_id": info['pin_id'],
            "url": IMAGE_URL_TPL.format(file_key=info['file']['key']),
            'type': info['file']['type'],
            'ext': ext,
            "title": info['raw_text'],
            "link": info['link'],
            "source": info['source'],
            "file_name": file_name
        }
        pins.append(meta)
    return pins


def get_boards(user_meta):
    boards = []
    for board in user_meta['boards']:
        meta = {
            "board_id": board['board_id'],
            "title": board['title'],
            "pins": None,
            "pin_count": board['pin_count'],
            "dir_name": _safe_file_name(board['title']),
        }
        boards.append(meta)
    return boards


def retry(max_retries=3):

    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            retries = 0
            while retries <= max_retries:
                retries += 1
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if retries > max_retries:
                        logging.exception("Error occurs while execute function\n")
                        break
            return None
        return wrapped

    return wrapper


@retry()
def do_request(method, *args, **kwargs):
    is_json = kwargs.pop('is_json', True)
    response = getattr(requests, method)(*args, timeout=(2, 10), **kwargs)
    if is_json:
        response.json()
        if _DEBUG:
            print("%s %s" % (method, str(args)))
    return response


class User(object):
    def __init__(self, user_url):
        self.session = requests.session()
        self.base_url = user_url
        self.further_url_tpl = urljoin(
            self.base_url,
            "?{random_str}"
            "&max={board_id}"
            "&limit=10"
            "&wfl=1"
        )

        self.username = None
        self.board_count = None
        self.pin_count = None
        self._boards = []

    def _fetch_home(self):
        resp = do_request("get", self.base_url, headers=XHR_HEADERS)
        user_meta = resp.json()['user']
        self.username = user_meta['username']
        self.board_count = user_meta['board_count']
        self.pin_count = user_meta['pin_count']
        return get_boards(user_meta)

    def _fetch_further(self, prev_boards):
        max_id = prev_boards[-1]['board_id']
        further_url = self.further_url_tpl.format(
            random_str=_random_string(8),
            board_id=max_id,
        )
        resp = do_request(
            "get",
            further_url,
            headers=XHR_HEADERS,
        )
        content = resp.json()
        return get_boards(content['user'])

    def _fetch_boards(self):
        self._boards.extend(self._fetch_home())
        while self.board_count > len(self._boards):
            further_boards = self._fetch_further(self.boards)
            self._boards.extend(further_boards)
        return self._boards

    @property
    def boards(self):
        if not self._boards:
            self._fetch_boards()
        return self._boards

    def as_dict(self):
        return {
            "username": self.username,
            "board_count": self.board_count,
            "boards": self.boards,
        }


class Board(object):
    def __init__(self, board_url_or_id):
        board_url_or_id = str(board_url_or_id)
        self.session = requests.session()
        if "http" in board_url_or_id:
            self.base_url = board_url_or_id
        else:
            self.base_url = "http://huaban.com/boards/{board_id}/".format(
                board_id=board_url_or_id
            )
        self.further_pin_url_tpl = urljoin(
            self.base_url,
            "?{random_string}"
            "&max={pin_id}"
            "&limit=20"
            "&wfl=1"
        )

        # uninitialized properties
        self.pin_count = None
        self.title = None
        self.description = None
        self._pins = []

    def _fetch_home(self):
        resp = do_request(
            "get",
            self.base_url,
            headers=XHR_HEADERS,
        )
        resp = resp.json()
        board = resp['board']
        self.pin_count = board['pin_count']
        self.title = board['title']
        self.description = board['description']
        return get_pins(board)

    def _fetch_further(self, prev_pins):
        max_id = prev_pins[-1]['pin_id']
        further_url = self.further_pin_url_tpl.format(
            pin_id=max_id,
            random_string=_random_string(8),
        )

        resp = do_request(
            "get",
            further_url,
            headers=XHR_HEADERS,
        )
        content = resp.json()
        return get_pins(content['board'])

    def fetch_pins(self):
        self._pins.extend(self._fetch_home())
        yield self._pins
        while self.pin_count > len(self._pins):
            further_pins = self._fetch_further(self._pins)
            if len(further_pins) <= 0:
                break
            self._pins.extend(further_pins)
            yield further_pins

    @property
    def pins(self):
        for pin_group in self.fetch_pins():
            for pin in pin_group:
                yield pin

    def as_dict(self):
        return {
            "pins": self._pins,
            "title": self.title,
            "description": self.description,
            "pin_count": self.pin_count,
        }


class Pin(object):
    def __init__(self, pin_meta, dir_to_save):
        self.url = pin_meta["url"]
        filename = u"{title}.{ext}".format(
            title=pin_meta['pin_id'],
            ext=pin_meta['ext'],
        )
        self.file_to_save = os.path.join(
            dir_to_save,
            filename,
        )


class HuaBan(object):
    def __init__(self, user_url):
        self.meta = None
        self.base_url = user_url
        self.user = User(user_url)
        self._boards = []
        self.parsed_pin_count = 0

    def fetch_initial_meta(self):
        boards = self.user.boards
        for meta in boards:
            self._boards.append(Board(meta['board_id']))

    @property
    def boards_pins(self):
        for board in self._boards:
            for pin in board.pins:
                yield board, pin

    def as_dict(self):
        meta = self.user.as_dict()
        meta['boards'] = [
            board.as_dict() for board in self._boards
        ]
        return meta

    def save_meta(self, file_name):
        meta = self.as_dict()
        json.dump(meta, open(file_name, "wb"))


class Worker(Thread):

    def __init__(
            self, queue, target
    ):
        """
        :type queue: Queue.Queue
        """
        super(Worker, self).__init__()
        self.task_func = target
        self.queue = queue
        self.daemon = True
        self._stopped = False

    def run(self):
        while not self._stopped:
            try:
                task = self.queue.get(timeout=60)
            except Queue.Empty:
                break
            else:
                self.task_func(*task)

    def stop(self):
        self._stopped = True


class Downloader(object):

    def __init__(self, user_url, workers=5):
        self.huaban = HuaBan(user_url)
        self.huaban.fetch_initial_meta()
        self.root_dir = _safe_file_name(self.huaban.user.username)
        self.progress_bar = None
        self.queue = Queue.Queue()
        self.workers = tuple(
            Worker(self.queue, self.download_one)
            for x in xrange(workers)
        )

    def download_one(self, pin, dir_to_save):
        import logging
        pin = Pin(pin, dir_to_save)
        response = do_request("get", pin.url, is_json=False)
        if response is None:
            logging.error("Failed to download image: %s" % pin.url)
        with open(pin.file_to_save, "wb") as f:
            f.write(response.content)
            self.progress_bar.update(1)

    def get_board_dir(self, board):
        """
        :type board: Board
        """
        board_title = board.title.replace("/", "_")
        return os.path.join(self.root_dir, board_title)

    def start(self):
        self.progress_bar = tqdm(total=self.huaban.user.pin_count)

        if not os.path.exists(self.root_dir):
            os.mkdir(self.root_dir)

        for worker in self.workers:
            worker.start()

        self._fetch_boards_meta()

    def _fetch_boards_meta(self):
        for board, pin in self.huaban.boards_pins:
            path = self.get_board_dir(board)
            if not os.path.exists(path):
                os.mkdir(path)
            self.queue.put(
                (pin, path)
            )
        self.save()

    def save(self):
        meta_file = os.path.join(self.root_dir, "meta.json")
        self.huaban.save_meta(meta_file)

    def stop(self):
        for worker in self.workers:
            worker.stop()

    def join(self):
        for worker in self.workers:
            worker.join()


def start_download(user_url, workers):
    print("Fetching initial meta data from huaban...")
    downloader = Downloader(user_url, workers=workers)
    print("Downloading pins from HuaBan with %s workers..." % workers)
    downloader.start()

    while not downloader.queue.empty():
        try:
            sleep(10)
        except KeyboardInterrupt:
            print("User exit")
            break
    downloader.save()
    print("Meta data download completed and saved in meta.json")
    downloader.stop()
    downloader.join()


@cmd.argument("board-url")
@cmd.command("fetch-board")
def fetch_board(board_url):
    board = Board(board_url)
    pins = list(board.pins)
    pprint(pins)
    pprint("pin_length is %s, pin_count is %s" % (len(pins), board.pin_count))


@cmd.argument("user-url")
@cmd.command("fetch-user")
def fetch_user(user_url):
    user = User(user_url)
    boards = list(user.boards)
    pprint(boards)


@cmd.argument("user-url")
@cmd.option("debug", is_flag=True, default=False)
@cmd.command("fetch-meta")
def fetch_meta(user_url, debug):
    global _DEBUG
    _DEBUG = debug
    huaban = HuaBan(user_url)
    huaban.fetch_initial_meta()
    board_pins = list(huaban.boards_pins)
    pprint(huaban.as_dict())
    pprint("pins length is %s" % len(board_pins))


@cmd.argument("user-url")
@cmd.option("workers", type=cmd.INT, default=5, help="Number of download workers.")
@cmd.option("debug", is_flag=True, default=False)
@cmd.command("download")
def download(user_url, workers, debug):
    global _DEBUG
    _DEBUG = debug
    start_download(user_url, workers=workers)


if __name__ == "__main__":
    cmd.entry()
