import re
import requests
import cmdtree as cmd

class User(object):
    def __init__(self, user_uid):
        self.uid = user_uid
        self.user_home = "http://huaban.com/{user_uid}".format(
            user_uid=self.uid,
        )

    def get_baords(self):
        pass

    
class Board(object):
    def __init__(self, board_id):
        self.session = requests.session()
        self.base_url = "http://huaban.com/boards/{baord_id}/".format(
            board_id=board_id,
        )
        self.pin_regx = re.compile(r'app\.page\["pins"\].*')
        self.image_tpl = "http://img.hb.aicdn.com/{file_key}_fw658"

    def fetch_home(self):
        resp = self.session.get(self.base_url)
        page_content = resp.content

        pins = prog.findall(page_content)
        result = eval(pins[0][19:-1])
        images = []
        for meta in result:
            info = {}
            info['id'] = str(meta['pin_id'])
            info['url'] = self.image_tpl.format(file_key=meta['file']['key'])
            info['type'] = meta['file']['type'][6:]
            images.append(info)
        return images


@cmd.argument("board_id", type=cmd.INT)
@cmd.command()
def board(board_id):
    board = Board(board_id)
    print board.fetch_home()

if __name__ == "__main__":
    cmd.entry()
