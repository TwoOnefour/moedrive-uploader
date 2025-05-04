# @Time    : 2025/5/4 00:49
# @Author  : TwoOnefour
# @blog    : https://www.voidval.com
# @Email   : twoonefour@voidval.com
# @File    : main.py
import json
import os.path
from time import sleep

from requests import Session, get
from urllib.parse import quote_plus
import sqlite3

class Uploader:
    def __init__(self):
        self.session = None
        self.group_dict = {
            "萌社区成员 - 核心萌": 9,
            "萌社区成员 - 活跃萌": 6,
            "萌社区成员 - 潜水萌": 3,
            "非萌社区成员": 1
        }
        self.group = None
        self.trackers = None
        self.cursor = None
        self.conn = None

    def downloading_by_url(self, url: str, dst: str = "/动画", preferred_node: int = 0):
        _flag = False
        if url.startswith('http'):
            _flag = True
        elif url.startswith('magnet'):
            _flag = True

        if not _flag:
            print("The url you provided is invalid.")
            return
        self.session.post('https://pan.moe/api/v3/aria2/url',
                          json={
                              "url": [url],
                              "preferred_node": preferred_node,
                              "dst": dst
                          })

    def batch_downloading_by_url(self, urls: list, dst: str = "/动画", preferred_node: int = 0):
        self.session.post('https://pan.moe/api/v3/aria2/url',
                          json={
                              "url": urls,
                              "preferred_node": preferred_node,
                              "dst": dst
                          })

    def list_downloading_tasks(self) -> list:
        res = self.session.get("https://pan.moe/api/v3/aria2/downloading")
        if res and res.status_code == 200:
            _json = res.json()
            data = _json['data']
            for task in data:
                if task['status'] == 7:
                    # seeding file or transferring.
                    if task['info']['bittorrent']['mode'] == "multi":
                        if self.check_multi_file_transfer_status(
                            path=task['dst'] + '/' + task['info']['bittorrent']['info']['name'],
                            size=task['total'],
                            num=len(task['info']['files'])
                        ):
                            print(f"Task {task['info']['bittorrent']['info']['name']} is finished!")
                            self.delete_task(task['info']['gid'])
                            continue
                    elif self.check_single_file_transfer_status(
                            path=task['dst'],
                            size=task['total'],
                            name=task['info']['bittorrent']['info']['name']
                        ):
                        print(f"Task {task['info']['bittorrent']['info']['name']} is finished!")
                        self.delete_task(task['info']['gid'])
                        continue

                    print(f"Task {task['info']['bittorrent']['info']['name']} is transferring. Total files: {len(task['info']['files'])}")
                elif task['status'] == 1:
                    if task['info']['bittorrent']['mode'] == "":
                        # no metadata fetched
                        print(
                            f"MetaData of this task is fetching...")
                    else:
                        print(f"Task {task['info']['bittorrent']['info']['name']} is downloading. {task['downloaded'] / task['total'] * 100:.2f}% complete.")

            return data

    def delete_task(self, task_gid: str):
        self.session.delete(f'https://pan.moe/api/v3/aria2/task/{task_gid}')
        # If fail, re join the queue
        self.cursor.execute(
            """
            DELETE FROM downloading_tasks WHERE gid = ?
            """,
            [task_gid]
        )


    def logout(self):
        if not self.session:
            return
        res = self.session.delete("https://pan.moe/api/v3/user/session")
        if res and res.status_code == 200:
            print("Logged out.")
        return res

    def login(self, username: str, password: str):
        if os.path.exists("cookie.txt"):
            with open("cookie.txt") as f:
                self.login_by_cookie(f.read())
            if self.session:
                return

        _session = Session()
        _session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0'})

        res = _session.post("https://pan.moe/api/v3/user/session", json={
            "userName": username,
            "Password": password,
            "captchaCode":""
        })
        if res.status_code != 200:
            raise Exception('Login failed. Please check your credentials.')
        self.session = _session
        print(f'Welcome back {res.json()['data']['nickname']}. You are in group {res.json()['data']['group']['name']}.')
        if res.json()['data']['group']['name'] in self.group_dict:
            self.group = res.json()['data']['group']['name']
        else:
            self.group = '非萌社区成员'
        self.save_cookie()

    def login_by_cookie(self, cookie):
        _session = Session()
        _session.headers.update(
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0',
                "Cookie": cookie
            }
        )
        if self.check_session_valid(_session):
            self.session = _session
            return True
        else:
            return False

    def check_session_valid(self, session):
        return True if session.get("https://pan.moe/api/v3/directory%2F").json()['code'] == 200 else False

    def save_cookie(self):
        if self.session and self.session.cookies:
            with open('cookie.txt', 'w') as f:
                cookie_header = "; ".join([f"{k}={v}" for k, v in self.session.cookies.items()])
                f.write(cookie_header)
            return
        raise Exception('Session failed.')

    def check_multi_file_transfer_status(self, path, size, num):
        # path = 'endpoint api' + json.data.dst + '/' +  json.data.info.bittorrent.info.name
        id = self.session.get(f"https://pan.moe/api/v3/directory{path}").json()['data']['parent']
        res = self.session.get(f"https://pan.moe/api/v3/object/property/{id}?trace_root=false&is_folder=true")
        current_size = res.json()['data']['size']
        current_num = res.json()['data']['child_file_num']
        if size == current_size and num == current_num:
            return True
        return False

    def check_single_file_transfer_status(self, path, size, name):
        objs = self.session.get(f"https://pan.moe/api/v3/directory{path}").json()['data']['objects']
        for item in objs:
            if item['name'] == name:
                current_size = item['size']
                if size == current_size:
                    return True

        return False

    def delete_all_finished(self):
        res = self.session.get(f"https://pan.moe/api/v3/aria2/finished?page=1")
        while len(res.json()['data']) != 0:
            for task in res.json()['data']:
                if task['status'] == 4:
                    self.delete_task(task['gid'])
                else:
                    self.delete_task_and_rejoin(task['gid'])
            res = self.session.get(f"https://pan.moe/api/v3/aria2/finished?page=1")
        self.conn.commit()

    def delete_task_and_rejoin(self, task_gid):
        self.cursor.execute(
            """
            SELECT * FROM downloading_tasks WHERE gid = ?
            """,
            task_gid
        )
        res = self.cursor.fetchone()
        self.downloading_by_url(url=self.get_magnet(res[1]))

    def get_trackers(self):
        trs = get("https://gh.voidval.com/https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt").text
        tr = ""
        trs_list = trs.split('\n\n')
        trs_list_len = len(trs_list)
        for i, _tr in enumerate(trs_list):
            if _tr.strip() != "":
                tr += "tr=" +  quote_plus(_tr)
                if i < trs_list_len - 2:
                    tr += "&"
        return tr

    def sql_init(self):
        if not self.cursor:
            self.conn = sqlite3.connect('lite.db')
            self.cursor = self.conn.cursor()
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS tasks (
                url TEXT PRIMARY KEY
            )
            '''
        )
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS downloading_tasks (
                gid TEXT PRIMARY KEY,
                url TEXT
            )
            '''
        )

    def sql_import(self):
        with open("urls", "r") as f:
            urls = f.readlines()
            if len(urls) == 0:
                return
            urls = [[url.strip("\n")] for url in urls]
            self.cursor.executemany(
                '''
                INSERT INTO tasks (url) VALUES (?) ON CONFLICT DO NOTHING;
                ''',
                urls
            )
            self.conn.commit()

        # clear the urls
        with open("urls", "w") as f:
            f.write("")

    def get_magnet(self, url):
        if self.trackers is None:
            self.trackers = self.get_trackers()
        return f"magnet:?xt=urn:btih:{url}" + "&" + self.trackers

    def add_tasks(self):
        count = self.get_current_tasks_count()
        if self.group_dict[self.group] - count == 0:
            print("You have met the threshold in your group. No tasks added.")
            return
        self.cursor.execute(
            f"""
            SELECT * FROM tasks limit {self.group_dict[self.group] - count};
            """
        )
        raw_tasks = [task[0] for task in self.cursor.fetchall()]
        tasks = [self.get_magnet(task) for task in raw_tasks]
        self.batch_downloading_by_url(tasks)
        self.add_tasks_to_downloading_table_sql([[task] for task in raw_tasks])

    def add_tasks_to_downloading_table_sql(self, lst):
        self.cursor.executemany(
            """
            DELETE FROM tasks where url = (?);
            """,
            lst
        )
        self.cursor.executemany(
            """
            INSERT INTO downloading_tasks (gid, url) VALUES (?, ?)
            """,
            [[self.get_gid_by_hashinfo(l[0]), l[0]] for l in lst]
        )


    def get_gid_by_hashinfo(self, url):
        sleep(2) # wait the data sync
        js = self.session.get("https://pan.moe/api/v3/aria2/downloading").json()['data']
        for task in js:
            if task['info']['infoHash'] == url:
                return task['info']['gid']


    def get_current_tasks_count(self):
        return len(self.list_downloading_tasks())

    def run(self):
        try:
            self.login(
                username="",
                password=""
            )
            self.sql_init()
            self.sql_import()
            # self.get_trackers()
            # self.list_downloading_tasks()
            self.delete_all_finished()
            self.add_tasks()
            # self.downloading_by_url(url="magnet:?xt=urn:btih:c1b386df63f5fa7619f7a1fa9be1873fcb84f8a5&dn=%5BVCB-Studio%5D%20Oregairu&tr=http%3A%2F%2Fwww.torrentsnipe.info%3A2701%2Fannounce&tr=http%3A%2F%2Ftracker810.xyz%3A11450%2Fannounce&tr=udp%3A%2F%2Fretracker01-msk-virt.corbina.net%3A80%2Fannounce&tr=http%3A%2F%2Ftracker.lintk.me%3A2710%2Fannounce&tr=udp%3A%2F%2Fisk.richardsw.club%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.xiaoduola.xyz%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.moxing.party%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.skyts.net%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.gbitt.info%3A80%2Fannounce&tr=http%3A%2F%2Ftracker.vanitycore.co%3A6969%2Fannounce&tr=udp%3A%2F%2Fleet-tracker.moe%3A1337%2Fannounce&tr=http%3A%2F%2Ftracker.ipv6tracker.org%3A80%2Fannounce&tr=https%3A%2F%2Ftracker.gbitt.info%2Fannounce&tr=http%3A%2F%2Fwww.genesis-sp.org%3A2710%2Fannounce&tr=http%3A%2F%2Ftracker.sbsub.com%3A2710%2Fannounce&tr=http%3A%2F%2Fbtracker.top%3A11451%2Fannounce&tr=http%3A%2F%2F97.117.114.88%3A9000%2Fannounce&tr=http%3A%2F%2Fsukebei.tracker.wf%3A8888%2Fannounce&tr=https%3A%2F%2F1337.abcvg.info%3A443%2Fannounce&tr=udp%3A%2F%2Fipv4.tracker.harry.lu%3A80%2Fannounce&tr=udp%3A%2F%2F163.172.29.130%3A80%2Fannounce&tr=http%3A%2F%2Ftracker.electro-torrent.pl%2Fannounce&tr=udp%3A%2F%2F95.31.11.224%3A6969%2Fannounce&tr=udp%3A%2F%2Fdenis.stalker.upeer.me%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.martlet.tk%3A6969%2Fannounce&tr=http%3A%2F%2Fbt.unionpeer.org%3A777%2Fannounce&tr=udp%3A%2F%2Fbedro.cloud%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrents.linuxmint.com%3A80%2Fannounce.php&tr=http%3A%2F%2Fbt.ali213.net%3A8000%2Fannounce&tr=https%3A%2F%2Ftracker.shittyurl.org%3A443%2Fannounce&tr=udp%3A%2F%2Ftorrents.artixlinux.org%3A6969%2Fannounce&tr=http%3A%2F%2Ffinbytes.org%2Fannounce.php&tr=udp%3A%2F%2Ftracker.arcbox.cc%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.tasvideos.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.gigantino.net%3A6969%2Fannounce&tr=http%3A%2F%2Fopen.touki.ru%2Fannounce&tr=udp%3A%2F%2F185.44.82.25%3A1337%2Fannounce&tr=https%3A%2F%2Ftracker.loligirl.cn%3A443%2Fannounce&tr=wss%3A%2F%2Ftracker.openwebtorrent.com%3A443%2Fannounce&tr=http%3A%2F%2Fpeersteers.org%3A80%2Fannounce&tr=udp%3A%2F%2F52.58.128.163%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker.lilithraws.org%3A443%2Fannounce&tr=https%3A%2F%2Ftr.abiir.top%2Fannounce&tr=udp%3A%2F%2Fmail.artixlinux.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftamas3.ynh.fr%3A6969%2Fannounce&tr=udp%3A%2F%2Fpublic.popcorn-tracker.org%3A6969%2Fannounce&tr=udp%3A%2F%2F192.95.46.115%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.moeking.me%3A6969%2Fannounce&tr=udp%3A%2F%2Fopentracker.i2p.rocks%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.ali213.net%3A8080%2Fannounce&tr=udp%3A%2F%2Fsugoi.pomf.se%3A80%2Fannounce&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2F209.126.11.233%3A6969%2Fannounce&tr=udp%3A%2F%2F5.196.89.204%3A6969%2Fannounce&tr=http%3A%2F%2Fbt.endpot.com%3A80%2Fannounce&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce&tr=udp%3A%2F%2F5.196.67.51%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.renfei.net%3A8080%2Fannounce&tr=http%3A%2F%2Ftracker.tfile.co%3A80%2Fannounce&tr=http%3A%2F%2Ftracker.kali.org%3A6969%2Fannounce&tr=udp%3A%2F%2F93.104.214.40%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.tfile.me%3A80%2Fannounce&tr=http%3A%2F%2Fopen.acgtracker.com%3A1096%2Fannounce&tr=https%3A%2F%2Ftracker.kuroy.me%3A443%2Fannounce&tr=udp%3A%2F%2Fbt.ktrackers.com%3A6666%2Fannounce&tr=udp%3A%2F%2Fopenbittorrent.com%3A80%2Fannounce&tr=http%3A%2F%2Ftracker.zerobytes.xyz%3A1337%2Fannounce&tr=http%3A%2F%2Fwww.thevault.bz%3A2810%2Fannounce&tr=udp%3A%2F%2Fzephir.monocul.us%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker3.dler.org%3A2710%2Fannounce&tr=udp%3A%2F%2Fmovies.zsw.ca%3A6969%2Fannounce&tr=http%3A%2F%2Fbt.firebit.org%3A2710%2Fannounce&tr=udp%3A%2F%2Ftracker.artixlinux.org%3A6969%2Fannounce&tr=udp%3A%2F%2Faegir.sexy%3A6969%2Fannounce&tr=udp%3A%2F%2F185.100.85.201%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrentsmd.com%3A8080%2Fannounce&tr=udp%3A%2F%2F82.65.115.10%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.altrosky.nl%3A6969%2Fannounce&tr=udp%3A%2F%2Fuploads.gamecoast.net%3A6969%2Fannounce&tr=udp%3A%2F%2F45.9.60.30%3A6969%2Fannounce&tr=udp%3A%2F%2F51.158.144.42%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.peckservers.com%3A9000%2Fannounce&tr=https%3A%2F%2Ftrackers.mlsub.net%3A443%2Fannounce&tr=http%3A%2F%2Ftracker.frozen-layer.com%3A6969%2Fannounce&tr=udp%3A%2F%2F46.138.242.240%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.thegeeks.bz%3A3210%2Fannounce&tr=http%3A%2F%2Fbig-boss-tracker.net%2Fannounce.php&tr=https%3A%2F%2Ftracker.torrentsnows.com%3A443%2Fannounce&tr=http%3A%2F%2Firrenhaus.dyndns.dk%3A80%2Fannounce.php&tr=http%3A%2F%2Fwww.freerainbowtables.com%3A6969%2Fannounce&tr=udp%3A%2F%2F51.81.222.188%3A6969%2Fannounce&tr=http%3A%2F%2Fservandroidkino.ru%2Fannounce&tr=https%3A%2F%2Ft1.hloli.org%3A443%2Fannounce&tr=http%3A%2F%2Fbt.3dmgame.com%3A2710%2Fannounce&tr=http%3A%2F%2Falpha.torrenttracker.nl%3A443%2Fannounce&tr=udp%3A%2F%2Ftracker.dump.cl%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.tribalmixes.com%3A80%2Fannounce.php&tr=http%3A%2F%2Fwww.all4nothin.net%3A80%2Fannounce.php&tr=https%3A%2F%2Ftracker.lilithraws.cf%2Fannounce&tr=http%3A%2F%2Fbttracker.debian.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.dler.com%3A6969%2Fannounce&tr=http%3A%2F%2F45.77.26.200%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.iamhansen.xyz%3A2000%2Fannounce&tr=http%3A%2F%2Ftorrent.resonatingmedia.com%3A6969%2Fannounce&tr=udp%3A%2F%2F37.187.95.112%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.nighthawk.pw%3A4201%2Fannounce&tr=udp%3A%2F%2F38.7.201.142%3A6969%2Fannounce&tr=http%3A%2F%2Fdata-bg.net%2Fannounce.php&tr=https%3A%2F%2Ftr.abir.ga%2Fannounce&tr=udp%3A%2F%2F107.189.11.58%3A6969%2Fannounce&tr=https%3A%2F%2Ftr.fuckbitcoin.xyz%3A443%2Fannounce&tr=udp%3A%2F%2Finferno.demonoid.is%3A3391%2Fannounce&tr=udp%3A%2F%2F144.91.88.22%3A6969%2Fannounce&tr=http%3A%2F%2Fbithq.org%2Fannounce.php&tr=udp%3A%2F%2F94.103.87.87%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrentzilla.org%2Fannounce&tr=https%3A%2F%2Ftracker.imgoingto.icu%3A443%2Fannounce&tr=http%3A%2F%2Fbt.zlofenix.org%3A81%2Fannounce&tr=udp%3A%2F%2Ftracker.leech.ie%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.darkness.services%3A6969%2Fannounce&tr=udp%3A%2F%2F135.181.197.114%3A1337%2Fannounce&tr=http%3A%2F%2Fbaibako.tv%2Fannounce&tr=http%3A%2F%2Ftk.greedland.net%2Fannounce&tr=http%3A%2F%2Ffreerainbowtables.com%3A6969%2Fannounce&tr=http%3A%2F%2F156.234.201.18%3A80%2Fannounce&tr=udp%3A%2F%2F51.159.54.68%3A6666%2Fannounce&tr=udp%3A%2F%2Faion.feralhosting.com%3A13337%2Fannounce&tr=http%3A%2F%2Fsecure.pow7.com%3A80%2Fannounce&tr=http%3A%2F%2Fxbtrutor.com%3A2710%2Fannounce&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A80%2Fannounce&tr=udp%3A%2F%2Fchouchou.top%3A8080%2Fannounce&tr=http%3A%2F%2Fmontreal.nyap2p.com%3A8080%2Fannounce&tr=http%3A%2F%2Fbt2.54new.com%3A8080%2Fannounce&tr=udp%3A%2F%2Ftracker-2.msm8916.com%3A6969%2Fannounce&tr=udp%3A%2F%2Faarsen.me%3A6969%2Fannounce&tr=http%3A%2F%2Falltorrents.net%3A80%2Fbt%2Fannounce.php&tr=udp%3A%2F%2Fpublic.tracker.vraphim.com%3A6969%2Fannounce&tr=http%3A%2F%2Ft.nyaatracker.com%3A80%2Fannounce&tr=http%3A%2F%2Fannounce.partis.si%3A80%2Fannounce&tr=udp%3A%2F%2Fopen.dstud.io%3A6969%2Fannounce&tr=http%3A%2F%2Fbt.beatrice-raws.org%3A80%2Fannounce&tr=http%3A%2F%2Fwww.all4nothin.net%2Fannounce.php&tr=udp%3A%2F%2Ftracker.0x7c0.com%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.gigatorrents.ws%3A2710%2Fannounce&tr=udp%3A%2F%2Frep-art.ynh.fr%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker.loligirl.cn%2Fannounce&tr=udp%3A%2F%2Ftracker.tricitytorrents.com%3A2710%2Fannounce&tr=http%3A%2F%2Ftorrent.mp3quran.net%3A80%2Fannounce.php&tr=udp%3A%2F%2Fepider.me%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker1.520.jp%2Fannounce&tr=udp%3A%2F%2Ftracker.breizh.pm%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.ds.is%3A6969%2Fannounce&tr=udp%3A%2F%2Fryjer.com%3A6969%2Fannounce&tr=https%3A%2F%2Ft.btcland.xyz%3A443%2Fannounce&tr=http%3A%2F%2Fproaudiotorrents.org%2Fannounce.php&tr=udp%3A%2F%2Fnew-line.net%3A6969%2Fannounce&tr=udp%3A%2F%2Fthagoat.rocks%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrents-nn.cn%3A2710%2Fannounce&tr=udp%3A%2F%2Ftracker.pimpmyworld.to%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrent.unix-ag.uni-kl.de%3A80%2Fannounce&tr=https%3A%2F%2Ftrackme.theom.nz%3A443%2Fannounce&tr=udp%3A%2F%2F45.130.21.69%3A6969%2Fannounce&tr=http%3A%2F%2Ftrackme.theom.nz%3A80%2Fannounce&tr=http%3A%2F%2Ftorrentsmd.eu%3A8080%2Fannounce&tr=udp%3A%2F%2Flaze.cc%3A6969%2Fannounce&tr=udp%3A%2F%2Ft.zerg.pw%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.skynetcloud.site%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.trancetraffic.com%3A80%2Fannounce.php&tr=udp%3A%2F%2F176.31.250.174%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.ololosh.space%3A6969%2Fannounce&tr=udp%3A%2F%2Fcarr.codes%3A6969%2Fannounce&tr=https%3A%2F%2Fevening-badlands-6215.herokuapp.com%2Fannounce&tr=udp%3A%2F%2F178.170.48.154%3A1337%2Fannounce&tr=https%3A%2F%2Fopen.acgnxtracker.com%3A443%2Fannounce&tr=wss%3A%2F%2Fpeertube.cpy.re%3A443%2Ftracker%2Fsocket&tr=udp%3A%2F%2Ftracker.uw0.xyz%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.tallpenguin.org%3A15800%2Fannounce&tr=udp%3A%2F%2F193.37.214.12%3A6969%2Fannounce&tr=udp%3A%2F%2F185.181.60.155%3A80%2Fannounce&tr=http%3A%2F%2Ftorrent.fedoraproject.org%3A6969%2Fannounce&tr=http%3A%2F%2Fmilliontorrent.pl%2Fannounce.php&tr=http%3A%2F%2Ftorrent.nwps.ws%2Fannounce&tr=udp%3A%2F%2Ftracker.dler.org%3A6969%2Fannounce&tr=udp%3A%2F%2F45.154.253.8%3A6969%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=http%3A%2F%2F1337.abcvg.info%2Fannounce&tr=udp%3A%2F%2Ftracker.qt.is%3A6969%2Fannounce&tr=udp%3A%2F%2Fretracker.coltel.ru%3A2710%2Fannounce&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A80%2Fannounce&tr=http%3A%2F%2Fxtremewrestlingtorrents.net%3A80%2Fannounce.php&tr=http%3A%2F%2Fanidex.moe%3A6969%2Fannounce&tr=udp%3A%2F%2F23.137.251.45%3A6969%2Fannounce&tr=udp%3A%2F%2Fopen.demonii.si%3A1337%2Fannounce&tr=http%3A%2F%2Fkinorun.com%2Fannounce.php&tr=https%3A%2F%2Fopentracker.i2p.rocks%3A443%2Fannounce&tr=udp%3A%2F%2F93.158.213.92%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce&tr=http%3A%2F%2Fretracker.telecom.by%3A80%2Fannounce&tr=udp%3A%2F%2Fv1046920.hosted-by-vdsina.ru%3A6969%2Fannounce&tr=udp%3A%2F%2Ftrackerb.jonaslsa.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fprivate.anonseed.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.bitsearch.to%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.cypherpunks.ru%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker3.ctix.cn%3A8080%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&tr=udp%3A%2F%2Ftracker.tiny-vps.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fp4p.arenabg.com%3A1337%2Fannounce&tr=http%3A%2F%2Ftracker4.itzmx.com%3A6961%2Fannounce&tr=http%3A%2F%2Ftracker.openbittorrent.com%3A80%2Fannounce&tr=udp%3A%2F%2F37.59.48.81%3A6969%2Fannounce&tr=http%3A%2F%2Fopen.acgnxtracker.com%3A80%2Fannounce&tr=http%3A%2F%2Fwww.theplace.bz%3A2910%2Fannounce&tr=udp%3A%2F%2F161.97.67.210%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.tvnihon.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fpublic.publictracker.xyz%3A6969%2Fannounce&tr=http%3A%2F%2Fretracker.mgts.by%3A80%2Fannounce&tr=http%3A%2F%2Fmvgroup.org%3A2710%2Fannounce&tr=http%3A%2F%2Ftracker.gbitt.info%2Fannounce&tr=udp%3A%2F%2Ftracker-de.ololosh.space%3A6969%2Fannounce&tr=udp%3A%2F%2Frun.publictracker.xyz%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.justseed.it%3A1337%2Fannounce&tr=udp%3A%2F%2Fbigfoot1942.sektori.org%3A6969%2Fannounce&tr=http%3A%2F%2Fpow7.com%3A80%2Fannounce&tr=http%3A%2F%2Fwww.bit-hdtv.com%3A2710%2Fannounce&tr=udp%3A%2F%2Ftracker.gmi.gd%3A6969%2Fannounce&tr=udp%3A%2F%2F185.230.4.150%3A1337%2Fannounce&tr=udp%3A%2F%2Fconcen.org%3A6969%2Fannounce&tr=http%3A%2F%2Fbluebird-hd.org%3A80%2Fannounce.php&tr=http%3A%2F%2Fwww.worldboxingvideoarchive.com%2Fannounce.php&tr=udp%3A%2F%2F185.102.219.163%3A6969%2Fannounce&tr=udp%3A%2F%2Fastrr.ru%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.thetradersden.org%2Fforums%2Ftracker%2Fannounce.php&tr=udp%3A%2F%2Fwww.torrent.eu.org%3A451%2Fannounce&tr=udp%3A%2F%2F45.33.36.106%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrent.arjlover.net%3A2710%2Fannounce&tr=udp%3A%2F%2F82.156.24.219%3A6969%2Fannounce&tr=udp%3A%2F%2F94.243.222.100%3A6969%2Fannounce&tr=udp%3A%2F%2Fopen.tracker.ink%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker.tamersunion.org%3A443%2Fannounce&tr=udp%3A%2F%2F148.251.53.72%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.srv00.com%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.torrentleech.org%3A2710%2Fannounce&tr=udp%3A%2F%2F35.227.12.84%3A1337%2Fannounce&tr=udp%3A%2F%2F45.156.24.123%3A6969%2Fannounce&tr=udp%3A%2F%2F51.15.26.25%3A6969%2Fannounce&tr=http%3A%2F%2Fbt-tracker.gamexp.ru%3A2710%2Fannounce&tr=https%3A%2F%2Ftracker.gbitt.info%3A443%2Fannounce&tr=http%3A%2F%2Fmixfiend.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fmoonburrow.club%3A6969%2Fannounce&tr=udp%3A%2F%2F89.36.216.8%3A6969%2Fannounce&tr=https%3A%2F%2Ftr.burnabyhighstar.com%3A443%2Fannounce&tr=udp%3A%2F%2F184.105.151.166%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker.jiesen.life%3A8443%2Fannounce&tr=udp%3A%2F%2Fretracker.hotplug.ru%3A2710%2Fannounce&tr=udp%3A%2F%2F176.56.3.118%3A6969%2Fannounce&tr=http%3A%2F%2F95.217.167.10%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.monitorit4.me%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker2.dler.org%3A80%2Fannounce&tr=udp%3A%2F%2Fsanincode.com%3A6969%2Fannounce&tr=https%3A%2F%2Ftr.ready4.icu%3A443%2Fannounce&tr=http%3A%2F%2Ftorrents.hikarinokiseki.com%3A6969%2Fannounce&tr=http%3A%2F%2Ft1.pow7.com%3A80%2Fannounce&tr=http%3A%2F%2Fblackz.ro%2Fannounce.php&tr=udp%3A%2F%2F51.15.3.74%3A6969%2Fannounce&tr=udp%3A%2F%2F95.216.74.39%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker1.bt.moack.co.kr%3A80%2Fannounce&tr=http%3A%2F%2Fsiambit.com%2Fannounce.php&tr=udp%3A%2F%2F104.131.98.232%3A6969%2Fannounce&tr=https%3A%2F%2Ftp.m-team.cc%3A443%2Fannounce.php&tr=http%3A%2F%2Ftracker.theempire.bz%3A3110%2Fannounce&tr=udp%3A%2F%2F167.99.185.219%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.tambovnet.org%3A80%2Fannounce.php&tr=http%3A%2F%2Fp2p.0g.cx%3A6969%2Fannounce&tr=udp%3A%2F%2F51.15.79.209%3A6969%2Fannounce&tr=http%3A%2F%2Fdatascene.net%3A80%2Fannounce.php&tr=http%3A%2F%2F0d.kebhana.mx%3A443%2Fannounce&tr=http%3A%2F%2Fretracker.spb.ru%3A80%2Fannounce&tr=udp%3A%2F%2Fpsyco.fr%3A6969%2Fannounce&tr=udp%3A%2F%2Fdownload.nerocloud.me%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.gcvchp.com%3A2710%2Fannounce&tr=http%3A%2F%2Fwww.bitseduce.com%2Fannounce.php&tr=http%3A%2F%2Fretracker.spark-rostov.ru%2Fannounce&tr=http%3A%2F%2Fa.leopard-raws.org%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrent-team.net%2Fannounce.php&tr=udp%3A%2F%2Ftorr.ws%3A2710%2Fannounce&tr=udp%3A%2F%2F6ahddutb1ucc3cp.ru%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=http%3A%2F%2Fwww.wareztorrent.com%2Fannounce&tr=udp%3A%2F%2Fthouvenin.cloud%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker3.itzmx.com%3A8080%2Fannounce&tr=udp%3A%2F%2Fpeerfect.org%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.linkomanija.org%3A2710%2Fannounce&tr=ws%3A%2F%2Ftracker.files.fm%3A7072%2Fannounce&tr=http%3A%2F%2Fall4nothin.net%2Fannounce.php&tr=udp%3A%2F%2F173.249.201.201%3A6969%2Fannounce&tr=http%3A%2F%2F159.69.65.157%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.mywaifu.best%3A6969%2Fannounce&tr=udp%3A%2F%2F91.216.110.53%3A451%2Fannounce&tr=udp%3A%2F%2F208.83.20.20%3A6969%2Fannounce&tr=udp%3A%2F%2F193.42.111.57%3A9337%2Fannounce&tr=udp%3A%2F%2Fopentracker.io%3A6969%2Fannounce&tr=http%3A%2F%2Fbt-club.ws%2Fannounce&tr=udp%3A%2F%2F179.43.155.30%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.zone-torrent.net%3A80%2Fannounce.php&tr=http%3A%2F%2F60-fps.org%3A80%2Fbt%2Fannounce.php&tr=udp%3A%2F%2Ftracker.fatkhoala.org%3A13790%2Fannounce&tr=udp%3A%2F%2F178.32.222.98%3A3391%2Fannounce&tr=udp%3A%2F%2Ftracker.btsync.gq%3A6969%2Fannounce&tr=http%3A%2F%2Fbtx.anifilm.tv%3A80%2Fannounce.php&tr=http%3A%2F%2Ft2.pow7.com%3A80%2Fannounce&tr=http%3A%2F%2Ftehconnection.eu%3A2790%2Fannounce&tr=http%3A%2F%2Fmasters-tb.com%3A80%2Fannounce.php&tr=http%3A%2F%2Ftracker.torrentbytes.net%2Fannounce.php&tr=udp%3A%2F%2Ftracker.auctor.tv%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.siambt.com%2Fannounce.php&tr=udp%3A%2F%2Ffe.dealclub.de%3A6969%2Fannounce&tr=http%3A%2F%2Fwww.legittorrents.info%3A80%2Fannounce.php&tr=https%3A%2F%2Ftracker.foreverpirates.co%3A443%2Fannounce&tr=http%3A%2F%2Ftracker.ddunlimited.net%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.theoks.net%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.torrenty.org%3A6969%2Fannounce&tr=https%3A%2F%2Fzer0day.000webhostapp.com%2Fannounce&tr=http%3A%2F%2Fwww.mvgroup.org%3A2710%2Fannounce&tr=http%3A%2F%2Ftracker.pow7.com%3A80%2Fannounce&tr=http%3A%2F%2Fatrack.pow7.com%3A80%2Fannounce&tr=http%3A%2F%2Fwww.megatorrents.kg%3A80%2Fannounce.php&tr=http%3A%2F%2Fhdreactor.org%3A2710%2Fannounce&tr=http%3A%2F%2Ftracker.xdvdz.com%3A2710%2Fannounce&tr=udp%3A%2F%2F135.125.106.92%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker1.itzmx.com%3A8080%2Fannounce&tr=udp%3A%2F%2F51.68.174.87%3A6969%2Fannounce&tr=udp%3A%2F%2F171.104.110.82%3A6969%2Fannounce&tr=udp%3A%2F%2Fseedbay.net%3A2710%2Fannounce&tr=udp%3A%2F%2Facxx.de%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.tfile.me%2Fannounce&tr=udp%3A%2F%2Ftracker.open-internet.nl%3A6969%2Fannounce&tr=udp%3A%2F%2Fexplodie.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.tryhackx.org%3A6969%2Fannounce&tr=https%3A%2F%2Ftracker.lilithraws.cf%3A443%2Fannounce&tr=https%3A%2F%2Ftracker.moeblog.cn%3A443%2Fannounce&tr=http%3A%2F%2Ftracker.frozen-layer.net%3A6969%2Fannounce.php&tr=udp%3A%2F%2F194.38.21.77%3A6969%2Fannounce&tr=udp%3A%2F%2F209.141.59.16%3A6969%2Fannounce&tr=udp%3A%2F%2F37.187.111.136%3A6969%2Fannounce&tr=http%3A%2F%2Fmvgforumtracker.mvgroup.org%3A80%2Ftracker.php%2Fannounce&tr=udp%3A%2F%2Ftracker2.dler.com%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.ccp.ovh%3A6969%2Fannounce&tr=udp%3A%2F%2Ffh2.cmp-gaming.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fhtz3.noho.st%3A6969%2Fannounce&tr=https%3A%2F%2Ftr.burnabyhighstar.com%2Fannounce&tr=udp%3A%2F%2Ftracker.filemail.com%3A6969%2Fannounce&tr=udp%3A%2F%2Fretracker.lanta-net.ru%3A2710%2Fannounce&tr=https%3A%2F%2Ftracker.m-team.cc%2Fannounce.php&tr=udp%3A%2F%2F185.134.22.3%3A6969%2Fannounce&tr=http%3A%2F%2Ftorrent.ubuntu.com%3A6969%2Fannounce&tr=udp%3A%2F%2F103.122.21.50%3A6969%2Fannounce&tr=udp%3A%2F%2F198.100.149.66%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.sylphix.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.qu.ax%3A6969%2Fannounce&tr=udp%3A%2F%2F88.99.2.212%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.christianbro.pw%3A6969%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.bittor.pw%3A1337%2Fannounce&tr=http%3A%2F%2F0d.kebhana.com.mx%3A443%2Fannounce&tr=udp%3A%2F%2F74.120.175.165%3A6969%2Fannounce&tr=http%3A%2F%2Ftracker.tfile.co%2Fannounce&tr=http%3A%2F%2Ftracker.minglong.org%3A8080%2Fannounce&tr=udp%3A%2F%2F220.130.15.30%3A6969%2Fannounce")

        except Exception as e:
            print(e)
        finally:
            # self.logout()
            if self.conn:
                self.conn.commit()
# 1 个任务创建失败：超出批量离线下载任务数量限制，请稍后再试（核心萌9个，活跃萌6个，潜水萌3个，非萌社区成员1个
# sql tables format : table tasks (text url, primary key url) downloading tasks (text gid,text url, primary key gid)
# tracker https://gh.voidval.com/https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt
Uploader().run()