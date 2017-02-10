#!/usr/bin/env python

import json
import os
import Queue
from threading import Thread
from time import sleep

import requests
from pprint import pprint
from urlparse import urljoin

import cmdtree as cmd
from tqdm import tqdm

IMAGE_URL_TPL = "http://img.hb.aicdn.com/{file_key}"
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; WOW64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/56.0.2924.87 Safari/537.36",
}


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
            "dir_name": _safe_file_name(board['title']),
        }
        boards.append(meta)
    return boards


class User(object):
    def __init__(self, user_url):
        self.session = requests.session()
        self.base_url = user_url
        self.further_url_tpl = urljoin(
            self.base_url,
            "?iyyi5hr3"
            "&max={board_id}"
            "&limit=10"
            "&wfl=1"
        )

        self.username = None
        self.board_count = None
        self.pin_count = None
        self.boards = []

    def _fetch_home(self):
        resp = self.session.get(self.base_url, headers=XHR_HEADERS)
        user_meta = resp.json()['user']
        self.username = user_meta['username']
        self.board_count = user_meta['board_count']
        self.pin_count = user_meta['pin_count']
        return get_boards(user_meta)

    def _fetch_further(self, prev_boards):
        max_id = prev_boards[-1]['board_id']
        further_url = self.further_url_tpl.format(
            board_id=max_id,
        )
        resp = self.session.get(
            further_url,
            headers=XHR_HEADERS,
        )
        content = resp.json()
        return get_boards(content['user'])

    def fetch_boards(self):
        self.boards.extend(self._fetch_home())
        while self.board_count > len(self.boards):
            further_boards = self._fetch_further(self.boards)
            self.boards.extend(further_boards)
        return self.boards

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
            "?iyqrlr0z"
            "&max={pin_id}"
            "&limit=20"
            "&wfl=1"
        )

        # uninitialized properties
        self.pin_count = None
        self.title = None
        self.description = None
        self.pins = []

    def _fetch_home(self):
        resp = self.session.get(
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
        )
        resp = self.session.get(
            further_url,
            headers=XHR_HEADERS,
        )
        content = resp.json()
        return get_pins(content['board'])

    def fetch_pins(self):
        self.pins.extend(self._fetch_home())
        while self.pin_count > len(self.pins):
            further_pins = self._fetch_further(self.pins)
            self.pins.extend(further_pins)
        return self.pins

    def as_dict(self):
        return {
            "pins": self.pins,
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
        self.boards = []

    def fetch_meta(self, sleep_time=0.1):
        self.user.fetch_boards()
        for meta in self.user.boards:
            self.boards.append(Board(meta['board_id']))
        for board in self.boards:
            sleep(sleep_time)
            board.fetch_pins()

    def as_dict(self):
        meta = self.user.as_dict()
        meta['boards'] = [
            board.as_dict() for board in self.boards
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
                task = self.queue.get(timeout=2)
            except Queue.Empty:
                break
            else:
                retries = 0
                while retries < 3:
                    try:
                        self.task_func(*task)
                        break
                    except Exception:
                        retries += 1
                        continue

    def stop(self):
        self._stopped = True


class Downloader(object):

    def __init__(self, user_url, workers=5):
        self.huaban = HuaBan(user_url)
        self.huaban.fetch_meta()
        self.root_dir = _safe_file_name(self.huaban.user.username)
        self.progress_bar = None
        self.queue = Queue.Queue()
        self.workers = tuple(
            Worker(self.queue, self.download_one)
            for x in xrange(workers)
        )

    def init_tasks(self):
        if not os.path.exists(self.root_dir):
            os.mkdir(self.root_dir)
        meta_file = os.path.join(self.root_dir, "meta.json")
        self.huaban.save_meta(meta_file)
        for board in self.huaban.boards:
            path = self.get_board_dir(board)
            if not os.path.exists(path):
                os.mkdir(path)
            pins = board.pins
            for pin in pins:
                self.queue.put(
                    (pin, path)
                )

    def download_one(self, pin, dir_to_save):
        pin = Pin(pin, dir_to_save)
        resp = requests.get(pin.url)
        with open(pin.file_to_save, "wb") as f:
            f.write(resp.content)
        self.progress_bar.update(1)

    def get_board_dir(self, board):
        """
        :type board: Board
        """
        board_title = board.title.replace("/", "_")
        return os.path.join(self.root_dir, board_title)

    def start(self):
        self.progress_bar = tqdm(total=self.huaban.user.pin_count)
        for worker in self.workers:
            worker.start()

    def stop(self):
        for worker in self.workers:
            worker.stop()

    def join(self):
        for worker in self.workers:
            worker.join()


def start_download(user_url, workers):
    print("Fetching meta data from huaban...")
    downloader = Downloader(user_url, workers=workers)
    print("Meta data downloaded and saved in meta.json")
    print("Downloading pins from HuaBan...")
    downloader.init_tasks()
    downloader.start()

    while not downloader.queue.empty():
        try:
            sleep(1)
        except KeyboardInterrupt:
            print("User exit")
            break
    downloader.stop()
    downloader.join()


@cmd.argument("board-url")
@cmd.command("fetch-board")
def fetch_board(board_url):
    board = Board(board_url)
    pins = board.fetch_pins()
    pprint(pins)


@cmd.argument("user-url")
@cmd.command("fetch-user")
def fetch_user(user_url):
    user = User(user_url)
    boards = user.fetch_boards()
    pprint(boards)


@cmd.argument("user-url")
@cmd.command("fetch-meta")
def fetch_meta(user_url):
    huaban = HuaBan(user_url)
    huaban.fetch_meta()
    pprint(huaban.as_dict())


@cmd.argument("user-url")
@cmd.option("workers", type=cmd.INT, default=5, help="Number of download workers.")
@cmd.command("download")
def download(user_url, workers):
    start_download(user_url, workers=workers)


if __name__ == "__main__":
    cmd.entry()
