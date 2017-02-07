import json
import re
import requests
import cmdtree as cmd

IMAGE_URL_TPL = "http://img.hb.aicdn.com/{file_key}"
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
}


class User(object):
    def __init__(self, user_uid):
        self.uid = user_uid
        self.user_home = "http://huaban.com/{user_uid}".format(
            user_uid=self.uid,
        )

    def get_baords(self):
        pass


def get_pins(board_dict):
    board = board_dict
    pins = []
    for info in board['pins']:
        print info
        meta = {
            "pin_id": info['pin_id'],
            "url": IMAGE_URL_TPL.format(file_key=info['file']['key']),
            'type': info['file']['type'],
            "title": info['raw_text'],
            "link": info['link'],
            "source": info['source'],
        }
        pins.append(meta)
    return pins

    
class Board(object):
    def __init__(self, board_id):
        self.session = requests.session()
        self.board_id = board_id
        self.base_url = "http://huaban.com/boards/{board_id}/".format(
            board_id=self.board_id,
        )
        self.further_pin_url_tpl = "http://huaban.com/boards/{board_id}/" \
                               "?iyqrlr0z" \
                               "&max={pin_id}" \
                               "&limit=20" \
                               "&wfl=1"

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
            board_id=self.board_id,
            pin_id=max_id,
        )
        resp = self.session.get(
            further_url,
            headers=XHR_HEADERS,
        )
        content = resp.json()
        return get_pins(content['board'])

    def get_pins(self):
        self.pins.extend(self._fetch_home())
        while self.pin_count > len(self.pins):
            further_pins = self._fetch_further(self.pins)
            self.pins.extend(further_pins)
        return self.pins


@cmd.argument("board_id", type=cmd.INT)
@cmd.command("fetch-board")
def fetch_board(board_id):
    board = Board(board_id)
    print board.get_pins()

if __name__ == "__main__":
    # cmd.entry()
    fetch_board(18295004)
