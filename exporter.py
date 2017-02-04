import json
import re
import requests
import cmdtree as cmd

IMAGE_URL_TPL = "http://img.hb.aicdn.com/{file_key}"


class User(object):
    def __init__(self, user_uid):
        self.uid = user_uid
        self.user_home = "http://huaban.com/{user_uid}".format(
            user_uid=self.uid,
        )

    def get_baords(self):
        pass


def get_pins(board_string):
    board = json.loads(board_string)
    pins = []
    for info in board['pins']:
        meta = {
            "pin_id": info['pin_id'],
            "url": IMAGE_URL_TPL.format(file_key=info['file']['key']),
            'type': info['file']['type'][6:]
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
        self.pin_regex = re.compile(r'app\.page\["board"\]\s=\s(.*?);')
        self.further_pin_url_tpl = "http://huaban.com/boards/{board_id}/" \
                               "?iyqrlr0z" \
                               "&max={pin_id}" \
                               "&limit=20" \
                               "&wfl=1"

    def fetch_home(self):
        resp = self.session.get(self.base_url)
        page_content = resp.content

        board_list = self.pin_regex.findall(page_content)
        board_str = board_list[0]
        return get_pins(board_str)

    def fetch_further(self, prev_pins):
        max_id = prev_pins[-1]['pin_id']
        further_url = self.further_pin_url_tpl.format(
            board_id=self.board_id,
            pin_id=max_id,
        )
        resp = self.session.get(
            further_url,
            headers={
                "X-Request": "JSON",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "http://huaban.com/boards/18295004/",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/55.0.2883.95 Safari/537.36",
                "DNT": "1",
                "Accept-Encoding": "gzip, deflate, sdch",
                "Accept-Language": "zh-CN,zh;q=0.8",
                "Pragma": "no-cache",

            }
        )
        content = resp.json()
        return get_pins(json.dumps(content['board']))


@cmd.argument("board_id", type=cmd.INT)
@cmd.command("fetch-board")
def fetch_board(board_id):
    board = Board(board_id)
    pins = board.fetch_home()
    print pins
    print board.fetch_further(prev_pins=pins)

if __name__ == "__main__":
    # cmd.entry()
    fetch_board(18295004)
